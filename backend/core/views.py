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

from core.exceptions import BusinessRuleError, CompanyRequired

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


_READY_PROBE_CACHE_KEY = "bizboard:ready_probe"
_READY_PROBE_TTL = 15


def probe_infra(*, use_cache: bool = True):
    """Cached (celery_ok, pdf_queue_depth, workers_ok, beat_ok).

    CORE-09: the underlying `_probe_celery_and_queue` broadcasts `inspect.ping`
    to every worker. `HealthView` is public, so cache the result for a few
    seconds — a burst of unauthenticated `?ready=1` requests then shares one
    control-plane round trip instead of one per request.
    """
    if use_cache:
        cached = cache.get(_READY_PROBE_CACHE_KEY)
        if cached is not None:
            return cached
    celery_ok, depth, workers_ok = _probe_celery_and_queue()
    beat_ok = _probe_celery_beat_ok()
    result = (celery_ok, depth, workers_ok, beat_ok)
    try:
        cache.set(_READY_PROBE_CACHE_KEY, result, _READY_PROBE_TTL)
    except Exception:  # noqa: BLE001 — cache write must not break the probe
        pass
    return result


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

        # CORE-09: authenticated owners get a fresh probe; everyone else (incl.
        # unauthenticated callers) gets the ~15s-cached result so a burst of
        # public `?ready=1` hits cannot hammer the Celery control plane.
        # CORE-10: a multi-membership user with no active company must not turn
        # a health check into a 409 — swallow CompanyRequired here.
        cu = None
        if getattr(request.user, "is_authenticated", False):
            try:
                cu = get_company_user(request)
            except Exception:  # noqa: BLE001 — health must not 409/403
                cu = None
        is_owner = cu is not None and getattr(cu, "role", None) == "OWNER"
        celery_ok, pdf_queue_depth, workers_ok, beat_ok = probe_infra(use_cache=not is_owner)
        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            beat_ok = True

        healthy = db_ok and cache_ok and celery_ok and beat_ok
        # BB-000626: unauthenticated / non-owner ready probe is boolean only.
        if not is_owner:
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
    mixins.DestroyModelMixin, viewsets.GenericViewSet,
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

    def get_permissions(self):
        # CORE-11: deleting a stored file (wrong upload / wrong kind) is
        # Owner-only — the coarse CanManageFileAssets gate lets sales/purchase
        # staff in, which is fine for upload/list but not for destroy.
        if self.action == "destroy":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return super().get_permissions()

    def perform_destroy(self, instance):
        # CORE-11: system-generated documents (invoice / note / challan PDFs,
        # import/export files) are regenerable or audit-relevant — only allow
        # deleting user attachments and logos.
        if instance.kind not in (FileAsset.Kind.ATTACHMENT, FileAsset.Kind.LOGO):
            raise BusinessRuleError(
                "Only uploaded attachments and logos can be deleted; "
                "system-generated documents are managed automatically."
            )
        stored = instance.file
        instance.delete()
        try:
            if stored:
                stored.delete(save=False)
        except Exception:  # noqa: BLE001 — row is already gone; orphan file is harmless
            pass

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

        cu = None
        if request.user and request.user.is_authenticated:
            try:
                cu = get_company_user(request)
            except CompanyRequired:
                cu = None
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
        # Unauthenticated metrics are never public — empty token means 404.
        if not token:
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
