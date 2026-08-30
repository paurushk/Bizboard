import hmac

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError

from .models import AuditEvent, FileAsset, Notification, StatutoryDocumentEvent
from .permissions import CanManageFileAssets, CanViewFinancialReports, HasCompany, IsOwner, get_company_user
from .serializers import (
    AuditEventSerializer,
    FileAssetSerializer,
    NotificationSerializer,
    StatutoryDocumentEventSerializer,
)
from .services.files import FileService

_HEALTH_CACHE_KEY = "bizboard:healthcheck"
_CELERY_QUEUE = "celery"

# BB-000753: process-local request counter for /metrics (plain text; no prometheus_client dep).
_REQUEST_COUNT = 0


def bump_request_count() -> None:
    global _REQUEST_COUNT
    _REQUEST_COUNT += 1


def get_request_count() -> int:
    return _REQUEST_COUNT


def _probe_celery_and_queue():
    """Return (celery_ok, pdf_queue_depth, workers_ok).

    BB-000218: Redis PING/LLEN alone is not worker liveness — require inspect.ping
    when not eager. Eager mode (tests/local) reports healthy with depth 0.
    """
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return True, 0, True

    depth = None
    redis_url = getattr(settings, "REDIS_URL", None) or getattr(settings, "CELERY_BROKER_URL", None)
    if redis_url:
        try:
            import redis

            client = redis.from_url(
                redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            client.ping()
            depth = int(client.llen(_CELERY_QUEUE))
        except Exception:  # noqa: BLE001 — probe must not raise
            pass

    workers_ok = False
    try:
        from config.celery import app

        insp = app.control.inspect(timeout=1.0)
        ping = insp.ping() if insp is not None else None
        workers_ok = bool(ping)
    except Exception:  # noqa: BLE001 — probe must not raise
        workers_ok = False

    celery_ok = workers_ok
    return celery_ok, depth, workers_ok


def _probe_celery_beat_ok():
    """BB-000359 / BB-000456: beat writes unix-epoch (or legacy ISO) heartbeat."""
    try:
        ts = cache.get("bizboard:celery_beat_heartbeat")
        if not ts:
            return False
        from datetime import datetime, timezone as dt_tz

        from django.utils import timezone

        if isinstance(ts, (int, float)):
            parsed = datetime.fromtimestamp(float(ts), tz=dt_tz.utc)
        elif isinstance(ts, str):
            raw = ts.strip()
            # Prefer unix epoch (compose.prod float() wire format).
            try:
                parsed = datetime.fromtimestamp(float(raw), tz=dt_tz.utc)
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    return False
        else:
            return False
        age = (timezone.now() - parsed).total_seconds()
        return age < 600  # 10 minutes
    except Exception:  # noqa: BLE001
        return False


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        want_ready = request.query_params.get("ready") in ("1", "true", "yes")
        # BB-000358: public liveness is minimal — no topology disclosure.
        if not want_ready:
            db_ok = False
            try:
                connection.ensure_connection()
                db_ok = True
            except Exception:  # noqa: BLE001
                db_ok = False
            return Response(
                {"status": "ok" if db_ok else "degraded", "version": "v1"},
                status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        db_ok = False
        cache_ok = False

        try:
            connection.ensure_connection()
            db_ok = True
        except Exception:  # noqa: BLE001 — probe must not raise
            db_ok = False

        try:
            cache.set(_HEALTH_CACHE_KEY, "1", 10)
            cache_ok = cache.get(_HEALTH_CACHE_KEY) == "1"
            try:
                from django_redis import get_redis_connection

                get_redis_connection("default").ping()
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            cache_ok = False

        celery_ok, pdf_queue_depth, workers_ok = _probe_celery_and_queue()
        beat_ok = _probe_celery_beat_ok()
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            beat_ok = True

        healthy = db_ok and cache_ok and celery_ok and beat_ok
        # BB-000626: unauthenticated / non-owner ready probe is boolean only.
        cu = get_company_user(request) if request.user.is_authenticated else None
        if not request.user.is_authenticated or cu is None or getattr(cu, "role", None) != "OWNER":
            return Response(
                {"status": "ok" if healthy else "degraded", "version": "v1"},
                status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        payload = {
            "status": "ok" if healthy else "degraded",
            "db": db_ok,
            "cache": cache_ok,
            "celery": celery_ok,
            "celery_workers": workers_ok,
            "celery_beat": beat_ok,
            "pdf_queue_depth": pdf_queue_depth,
            "rls_enabled": bool(getattr(settings, "POSTGRES_RLS_ENABLED", False)),
            "version": "v1",
        }
        http_status = (
            status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return Response(payload, status=http_status)


class FileAssetViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = FileAssetSerializer
    # BB-000421: VIEWER must not enumerate company PDFs / uploads.
    permission_classes = [IsAuthenticated, HasCompany, CanManageFileAssets]
    queryset = FileAsset.objects.all()

    def get_queryset(self):
        company = get_company_user(self.request).company
        qs = self.queryset.filter(company=company)
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)
        return qs

    def perform_create(self, serializer):
        uploaded = self.request.FILES.get("file")
        if not uploaded:
            raise BusinessRuleError("A file is required.")
        kind = serializer.validated_data.get("kind", FileAsset.Kind.ATTACHMENT)
        # BB-000499: magic-byte sniff before persisting (PDF %PDF, image headers).
        FileService.validate_upload(uploaded_file=uploaded, kind=kind)
        company = get_company_user(self.request).company
        serializer.instance = FileService.store_upload(
            company=company,
            uploaded_file=uploaded,
            kind=kind,
            user=self.request.user,
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        asset = self.get_object()
        try:
            handle = asset.file.open("rb")
        except (FileNotFoundError, OSError) as exc:
            raise Http404("File is no longer available.") from exc
        raw_name = (asset.original_name or "").replace("\r", "").replace("\n", "").replace('"', "").strip()
        safe_name = raw_name[:200] if raw_name else "download.bin"
        return FileResponse(handle, as_attachment=True, filename=safe_name)


class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, HasCompany]
    queryset = Notification.objects.all()

    def get_queryset(self):
        cu = get_company_user(self.request)
        qs = self.queryset.filter(company=cu.company)
        # Wave 12B: notifications are personal unless you're Owner — a Sales
        # Staff member should not see another staffer's SMS/email/WhatsApp log.
        if cu.role != "OWNER":
            qs = qs.filter(created_by=self.request.user)
        return qs


class AuditEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]
    queryset = AuditEvent.objects.all()

    def get_queryset(self):
        company = get_company_user(self.request).company
        qs = self.queryset.filter(company=company)
        action_filter = self.request.query_params.get("action")
        if action_filter:
            qs = qs.filter(action=action_filter)
        return qs


class StatutoryDocumentEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/v1/statutory-events/?entity_type=&entity_id="""

    serializer_class = StatutoryDocumentEventSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]
    queryset = StatutoryDocumentEvent.objects.all()

    def get_queryset(self):
        company = get_company_user(self.request).company
        qs = self.queryset.filter(company=company)
        entity_type = (self.request.query_params.get("entity_type") or "").strip()
        entity_id = (self.request.query_params.get("entity_id") or "").strip()
        event_type = (self.request.query_params.get("event_type") or "").strip()
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if entity_id:
            try:
                qs = qs.filter(entity_id=int(entity_id))
            except ValueError:
                qs = qs.none()
        return qs


class FeatureFlagsView(APIView):
    """GET /api/v1/feature-flags/ — runtime flags for FE boot.

    Anonymous callers receive a public subset. Authenticated callers receive
    env flags plus company overrides.
    """

    permission_classes = [AllowAny]

    _PUBLIC_FLAG_KEYS = ("ENABLE_SETUP_WIZARD",)

    def get(self, request):
        from core.services.feature_flags import build_feature_flags

        cu = get_company_user(request) if request.user and request.user.is_authenticated else None
        company = cu.company if cu is not None else None
        flags = build_feature_flags(
            company=company,
            user=request.user if request.user and request.user.is_authenticated else None,
        )
        if cu is None:
            flags = {k: bool(flags.get(k)) for k in self._PUBLIC_FLAG_KEYS}
        return Response(flags)


class MetricsView(APIView):
    """BB-000753: minimal Prometheus-style text counters (request count)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        token = (getattr(settings, "METRICS_TOKEN", "") or "").strip()
        env = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
        # R1-003: never serve an unauthenticated metrics endpoint in
        # production/staging — if no token is configured, the endpoint does
        # not exist as far as the outside world is concerned.
        if not token and env in ("production", "staging"):
            return HttpResponse(status=404)
        if token:
            auth = request.headers.get("Authorization", "")
            provided = auth[7:] if auth.startswith("Bearer ") else ""
            try:
                matched = bool(provided) and hmac.compare_digest(provided, token)
            except (TypeError, ValueError):
                matched = False
            if not matched:
                return HttpResponse(status=401)
        body = (
            "# HELP bizboard_http_requests_total Total HTTP requests handled by this process.\n"
            "# TYPE bizboard_http_requests_total counter\n"
            f"bizboard_http_requests_total {get_request_count()}\n"
        )
        return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")
