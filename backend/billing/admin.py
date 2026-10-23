from django.contrib import admin

from core.admin import RlsBypassAdminMixin, SuperuserOnlyAdminMixin

from .models import DeadLetterEvent, Plan, SaasTdsClaim, Subscription, TrialFingerprint


@admin.register(Plan)
class PlanAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "price_paise", "is_active")
    search_fields = ("name", "slug")
    fields = (
        "name", "slug", "price_paise", "modules", "seat_limit",
        "monthly_complete_limit", "storage_bytes_limit", "api_rate_per_minute",
        "razorpay_plan_id", "is_active",
    )


@admin.register(Subscription)
class SubscriptionAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("company", "plan", "status", "trial_ends_at", "razorpay_subscription_id")
    list_filter = ("status",)
    search_fields = ("razorpay_subscription_id",)


@admin.register(DeadLetterEvent)
class DeadLetterEventAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """9.5 gap fix: parked webhook/recon failures had no admin surface at all,
    so an operator could only discover or replay one by calling the API by
    hand. Read-only here (replay stays an explicit owner action via the API/
    SPA) -- this is for engineering to see what's stuck and why."""

    list_display = ("provider", "event_id", "company", "status", "attempts", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("event_id", "error")
    readonly_fields = [f.name for f in DeadLetterEvent._meta.fields]
    actions = ["replay_selected"]

    @admin.action(description="Replay selected parked events (pending only)")
    def replay_selected(self, request, queryset):
        """SET-06: replaying a parked billing webhook is operator work, so it lives here and no
        longer on the customer's Billing screen. Each replay is the same call the API makes."""
        from .services import replay_dead_letter

        done = failed = skipped = 0
        for event in queryset:
            if event.status != "pending":
                skipped += 1
                continue
            try:
                replay_dead_letter(event, user=request.user)
                done += 1
            except Exception as exc:  # noqa: BLE001 - report each failure, keep going
                failed += 1
                self.message_user(request, f"Event {event.event_id}: {exc}", level="error")
        self.message_user(request, f"Replayed {done}; {failed} failed; {skipped} not pending.")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SaasTdsClaim)
class SaasTdsClaimAdmin(RlsBypassAdminMixin, SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """WP-BL1: check each Form 16A against TRACES, then verify or reject. A verified credit claim
    comes off the company's next renewal; a refund claim is refunded at once (Q5)."""

    list_display = (
        "company", "quarter", "section", "amount", "settle_by", "credit_remaining", "status",
        "reviewed_by", "created_at",
    )
    list_filter = ("status", "settle_by", "quarter", "section")
    search_fields = ("company__name",)
    readonly_fields = [*[f.name for f in SaasTdsClaim._meta.fields], "invoices", "certificate_file"]
    actions = ["verify_and_refund_selected", "reject_selected"]
    list_select_related = ("company", "reviewed_by")

    @admin.display(description="Form 16A")
    def certificate_file(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        if not obj or not obj.certificate_id:
            return "-"
        url = reverse("admin:billing_saastdsclaim_certificate", args=[obj.pk])
        return format_html('<a href="{}" target="_blank" rel="noopener">Open the certificate</a>', url)

    def get_urls(self):
        from django.urls import path

        return [
            path("<int:pk>/certificate/", self.admin_site.admin_view(self.certificate_view),
                 name="billing_saastdsclaim_certificate"),
            *super().get_urls(),
        ]

    def certificate_view(self, request, pk: int):
        """Stream the uploaded Form 16A to staff so it can be checked against TRACES."""
        from django.http import FileResponse, Http404

        from core.rls import rls_bypass

        if not self.has_view_permission(request):
            raise Http404
        with rls_bypass():
            claim = SaasTdsClaim.objects.select_related("certificate").filter(pk=pk).first()
            if claim is None or claim.certificate is None or not claim.certificate.file:
                raise Http404
            asset = claim.certificate
            handle = asset.file.open("rb")
        return FileResponse(handle, as_attachment=False, filename=asset.original_name or f"form16a-{pk}")

    def has_add_permission(self, request):
        return False

    @admin.action(description="Certificate checked in TRACES: verify (credit or refund as the owner chose)")
    def verify_and_refund_selected(self, request, queryset):
        from core.rls import rls_bypass

        from .tds_claims import verify_claim

        with rls_bypass():
            for claim in queryset:
                try:
                    claim = verify_claim(claim, staff_user=request.user, note="Verified in TRACES")
                    outcome = "refunded" if claim.status == claim.Status.SETTLED else "credit for the next renewal"
                    self.message_user(request, f"Claim {claim.pk}: {claim.amount} {outcome}.")
                except Exception as exc:  # noqa: BLE001 - report each, keep going
                    self.message_user(request, f"Claim {claim.pk}: {exc}", level="error")

    @admin.action(description="Reject (certificate does not match TRACES)")
    def reject_selected(self, request, queryset):
        from core.rls import rls_bypass

        from .tds_claims import reject

        with rls_bypass():
            for claim in queryset:
                try:
                    reject(claim, staff_user=request.user, reason="The certificate does not match TRACES.")
                except Exception as exc:  # noqa: BLE001
                    self.message_user(request, f"Claim {claim.pk}: {exc}", level="error")


@admin.register(TrialFingerprint)
class TrialFingerprintAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """WP-AB3: hashed trial fingerprints. Delete a row to let that business start a new trial."""

    list_display = ("kind", "digest", "company_id_hint", "created_at")
    list_filter = ("kind",)
    readonly_fields = ("kind", "digest", "company_id_hint", "created_at")

    def has_add_permission(self, request):
        return False
