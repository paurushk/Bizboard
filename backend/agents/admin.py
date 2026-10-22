"""Ops views for agents live in Django admin (standing rule: never on the customer SPA)."""

from django.contrib import admin, messages

from .models import AgentAlias, AgentProposal, AgentRun, AgentStep


class AgentStepInline(admin.TabularInline):
    model = AgentStep
    extra = 0
    can_delete = False
    fields = ("seq", "kind", "tool_name", "duration_ms", "tokens_in", "tokens_out", "result_summary")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "agent", "trigger", "status", "error_code", "rules_only", "step_count", "tokens_in", "tokens_out", "created_at")
    list_filter = ("agent", "status", "trigger", "rules_only")
    search_fields = ("trigger_ref", "company__name")
    readonly_fields = [f.name for f in AgentRun._meta.fields]
    inlines = [AgentStepInline]
    actions = ["kill_switch_company"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Kill switch: turn agents OFF for the selected runs' companies")
    def kill_switch_company(self, request, queryset):
        from accounts.models import Company

        companies = Company.objects.filter(pk__in=queryset.values_list("company_id", flat=True).distinct())
        for company in companies:
            flags = dict(company.feature_flags or {})
            flags["ENABLE_AGENTS"] = False
            company.feature_flags = flags
            company.save(update_fields=["feature_flags", "updated_at"])
        self.message_user(request, f"Agents switched off for {companies.count()} company(ies).", messages.WARNING)


@admin.register(AgentProposal)
class AgentProposalAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "kind", "status", "title", "revision", "attempts", "failure_code", "expires_at", "created_at")
    list_filter = ("kind", "status")
    search_fields = ("dedupe_key", "title", "company__name")
    readonly_fields = [f.name for f in AgentProposal._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(AgentAlias)
class AgentAliasAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "scope", "raw_text_norm", "hits", "last_used_at")
    list_filter = ("scope",)
    search_fields = ("raw_text_norm",)


from insights.models import AiUsageLedger  # noqa: E402  (cost view for agents lives with the agents admin)


@admin.register(AiUsageLedger)
class AiUsageLedgerAdmin(admin.ModelAdmin):
    """Cost and token use. Filter by feature=AGENT and agent_kind to see spend per agent and company."""

    list_display = ("created_at", "company", "feature", "agent_kind", "model_name", "tokens_in", "tokens_out", "cost_display")
    list_filter = ("feature", "agent_kind", "model_name")
    date_hierarchy = "created_at"
    search_fields = ("company__name",)
    readonly_fields = [f.name for f in AiUsageLedger._meta.fields]

    def has_add_permission(self, request):
        return False

    @admin.display(description="Cost (USD)")
    def cost_display(self, obj):
        # B9-024: only agent calls are priced; everything else stays 0, which we show as "unpriced".
        return f"{obj.cost_estimate:.6f}" if obj.cost_estimate else "unpriced"
