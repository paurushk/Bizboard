import hmac

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.decorators import permission_classes as drf_permission_classes
from rest_framework.decorators import throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
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
# B7-020: read the queue name from Celery config so a future task_routes / a
# dedicated queue doesn't silently make the reported depth always 0.
_CELERY_QUEUE = getattr(settings, "CELERY_TASK_DEFAULT_QUEUE", None) or "celery"


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
        try:
            cached = cache.get(_READY_PROBE_CACHE_KEY)
        except Exception:  # noqa: BLE001 — QOS-0050: cache down must not 500 the health probe
            cached = None
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


class IntegrationsInventoryView(APIView):
    """Owner-only inventory of outbound integrations. Never returns secret values."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        from core.integration_inventory import INTEGRATIONS

        rows = []
        for row in INTEGRATIONS:
            present = {
                key: bool(getattr(settings, key, None)) for key in row["settings_keys"]
            }
            rows.append(
                {
                    "name": row["name"],
                    "sandbox": row["sandbox"],
                    "fallback": row["fallback"],
                    "money_path": row["money_path"],
                    "settings_present": present,
                }
            )
        return Response({"integrations": rows})


class InvariantsCheckView(APIView):
    """Owner/support surface for `check_invariants` against the active company."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        return self._run(request)

    def post(self, request):
        return self._run(request)

    def _run(self, request):
        from core.invariants import run_invariants

        company = get_company_user(request).company
        failures = run_invariants(company)
        ok = not failures
        return Response(
            {"ok": ok, "company_id": company.id, "failures": failures},
            status=status.HTTP_200_OK if ok else status.HTTP_409_CONFLICT,
        )


class HealthView(APIView):
    permission_classes = [AllowAny]
    # QOS-0050: a liveness / readiness probe must never be rate-limited, and must
    # not 500 just because the throttle cache (Redis) is the thing that is down.
    throttle_classes: list = []

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
            "sentry_configured": bool((getattr(settings, "SENTRY_DSN", "") or "").strip()),
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
        from billing.quotas import assert_storage_allowed

        assert_storage_allowed(company, additional_bytes=int(getattr(uploaded, "size", 0) or 0))
        serializer.instance = FileService.store_upload(
            company=company,
            uploaded_file=uploaded,
            kind=kind,
            user=self.request.user,
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        asset = self.get_object()
        # CORE-12: the list/retrieve gate (CanManageFileAssets) lets anyone with
        # sales OR purchase rights in — fine for their own attachments, but an
        # EXPORT / IMPORT file (tenant backups, bulk imports) should need the
        # export capability, and an OWNER always. Scope the actual download.
        cu = get_company_user(request)
        if asset.kind in (FileAsset.Kind.EXPORT, FileAsset.Kind.IMPORT):
            if not (cu and (cu.role == "OWNER" or cu.can_export or cu.can_import)):
                raise PermissionDenied(
                    "Downloading import/export files requires the export or import permission."
                )
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
        from core.ops_metrics import render_prometheus

        return HttpResponse(
            render_prometheus(),
            content_type="text/plain; version=0.0.4; charset=utf-8",
        )


def _company_for_flags(request):
    try:
        return get_company_user(request).company
    except CompanyRequired:
        return None


class TelegramStatusView(APIView):
    """GET /api/v1/telegram/status/ — this user's Telegram link state."""

    def get(self, request):
        from core.services.feature_flags import build_feature_flags

        flags = build_feature_flags(company=_company_for_flags(request), user=request.user)
        return Response(
            {
                "enabled": bool(flags.get("ENABLE_TELEGRAM")),
                "linked": bool(request.user.telegram_chat_id),
            }
        )


class TelegramLinkView(APIView):
    """POST /api/v1/telegram/link/ — issue a one-time /start deep link."""

    def post(self, request):
        from core.services.feature_flags import build_feature_flags
        from core.services.telegram import LINK_CODE_TTL, bot_deep_link, generate_link_code

        flags = build_feature_flags(company=_company_for_flags(request), user=request.user)
        if not flags.get("ENABLE_TELEGRAM"):
            raise BusinessRuleError("Telegram notifications are not enabled for this company.")
        if not (getattr(settings, "TELEGRAM_BOT_USERNAME", "") or "").strip():
            raise BusinessRuleError("Telegram bot is not configured (missing TELEGRAM_BOT_USERNAME).")

        code = generate_link_code(request.user)
        deep_link = bot_deep_link(code)
        return Response({"deep_link": deep_link, "expires_in": int(LINK_CODE_TTL.total_seconds())})


class TelegramUnlinkView(APIView):
    """POST /api/v1/telegram/unlink/ — disconnect this user's Telegram account."""

    def post(self, request):
        request.user.telegram_chat_id = ""
        request.user.telegram_link_code = ""
        request.user.telegram_link_code_expires_at = None
        request.user.save(
            update_fields=["telegram_chat_id", "telegram_link_code", "telegram_link_code_expires_at"]
        )
        return Response({"linked": False})


class TelegramWebhookThrottle(AnonRateThrottle):
    rate = "60/min"


@api_view(["POST"])
@drf_permission_classes([AllowAny])
@throttle_classes([TelegramWebhookThrottle])
def telegram_webhook(request):
    """POST /api/v1/telegram/webhook/ — /start <code> linking handshake only.

    This is not a two-way command bot: any update that isn't a recognized
    /start code is acknowledged and dropped.
    """
    secret = (getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or "").strip()
    provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secret or not hmac.compare_digest(provided, secret):
        return Response(status=status.HTTP_401_UNAUTHORIZED)

    message = (request.data or {}).get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None or not text.startswith("/start"):
        return Response({"ok": True})

    from core.services.telegram import link_chat_id, resolve_link_code, send_telegram_message

    parts = text.split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""
    user = resolve_link_code(code)
    if user is None:
        send_telegram_message(str(chat_id), "This link has expired. Generate a new one from Bizboard settings.")
        return Response({"ok": True})

    link_chat_id(user, str(chat_id))
    send_telegram_message(str(chat_id), "Bizboard is now connected. You'll receive alerts here.")
    return Response({"ok": True})


class OpsAlertWebhookThrottle(AnonRateThrottle):
    rate = "30/min"


def _ops_alert_text(payload: dict) -> str | None:
    """Format an alert-source payload into a short page. None = nothing worth paging on.

    Recognizes: Sentry's Internal Integration `event_alert` webhook shape,
    a generic {"message"|"text": "..."} shape (Healthchecks.io / UptimeRobot /
    any monitor that lets you template the POST body), and falls back to a
    truncated raw dump so nothing is silently swallowed.
    """
    if not isinstance(payload, dict):
        return None

    event = ((payload.get("data") or {}).get("event") or {}) if isinstance(payload.get("data"), dict) else {}
    if event:
        title = (event.get("title") or event.get("message") or "Sentry alert").strip()
        culprit = (event.get("culprit") or "").strip()
        url = (event.get("web_url") or event.get("url") or "").strip()
        rule = ((payload.get("data") or {}).get("triggered_rule") or "").strip()
        lines = [f"🔴 {title}"]
        if culprit:
            lines.append(culprit)
        if rule:
            lines.append(f"Rule: {rule}")
        if url:
            lines.append(url)
        return "\n".join(lines)[:4096]

    # Sentry also pings this URL for non-alert resources (installation
    # created/deleted) when the integration is first wired up — ack, don't page.
    if payload.get("installation") is not None and not event:
        return None

    text = (payload.get("message") or payload.get("text") or "").strip()
    if text:
        return text[:4096]

    if payload:
        import json

        return ("⚠️ Ops alert (unrecognized payload): " + json.dumps(payload)[:1500])
    return None


@api_view(["POST"])
@drf_permission_classes([AllowAny])
@throttle_classes([OpsAlertWebhookThrottle])
def ops_alert_webhook(request):
    """POST /api/v1/ops/alert/?token=... — generic no-infra paging relay.

    Point a Sentry Internal Integration's alert-rule webhook, or any uptime
    monitor (Healthchecks.io, UptimeRobot, ...) that lets you set the POST
    URL, at this endpoint with OPS_ALERT_TOKEN in the query string or an
    X-Ops-Alert-Token header. Relays a formatted message to the fixed
    OPS_TELEGRAM_CHAT_ID — a free stand-in for a dedicated on-call product.
    """
    configured = (getattr(settings, "OPS_ALERT_TOKEN", "") or "").strip()
    provided = request.query_params.get("token", "") or request.headers.get("X-Ops-Alert-Token", "")
    if not configured or not hmac.compare_digest(provided, configured):
        return Response(status=status.HTTP_401_UNAUTHORIZED)

    payload = request.data if isinstance(request.data, dict) else {}
    text = _ops_alert_text(payload)
    if text:
        from core.services.telegram import send_ops_alert

        send_ops_alert(text)
    return Response({"ok": True})
