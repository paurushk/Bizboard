from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        """CORE-14: guarantee a deterministic page order for every list view.

        A ``PageNumberPagination`` over a queryset with no ordering — or an
        ordering whose key is not unique (``-created_at`` on rows created in the
        same tick, ``-invoice_date`` for a day's invoices, …) — can drop or
        repeat rows across page boundaries. Append the primary key as a final
        tie-breaker so paging is stable regardless of what each view's
        ``get_queryset`` did (or forgot to do).
        """
        try:
            queryset = self._with_pk_tiebreak(queryset)
        except Exception:  # noqa: BLE001 — never let this break a list endpoint
            pass
        return super().paginate_queryset(queryset, request, view)

    @staticmethod
    def _with_pk_tiebreak(queryset):
        model = getattr(queryset, "model", None)
        if model is None:
            return queryset
        pk_name = model._meta.pk.name
        order_fields = list(queryset.query.order_by) or list(
            getattr(model._meta, "ordering", []) or []
        )
        bare = {f.lstrip("-") for f in order_fields}
        if pk_name in bare or "pk" in bare:
            return queryset
        # Mirror the direction of the last ordering key so the tie-break reads
        # naturally (newest-first lists stay newest-first within a tie).
        descending = bool(order_fields and order_fields[-1].startswith("-"))
        tiebreak = f"-{pk_name}" if descending else pk_name
        return queryset.order_by(*order_fields, tiebreak)
