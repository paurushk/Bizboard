from djangorestframework_camel_case.render import CamelCaseJSONRenderer


class EnvelopeJSONRenderer(CamelCaseJSONRenderer):
    """Wraps successful responses as {"success": true, "data": ...} and camelizes keys."""

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response") if renderer_context else None
        already_wrapped = isinstance(data, dict) and isinstance(data.get("success"), bool)
        if already_wrapped or (response is not None and response.exception):
            wrapped = data
        else:
            wrapped = {"success": True, "data": data}
        return super().render(wrapped, accepted_media_type, renderer_context)
