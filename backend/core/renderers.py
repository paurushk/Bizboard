from djangorestframework_camel_case.render import CamelCaseJSONRenderer


class EnvelopeJSONRenderer(CamelCaseJSONRenderer):
    """Wraps successful responses as {"success": true, "data": ...} and camelizes keys.

    Non-2xx responses that were returned via Response(..., status=4xx) without
    raising an exception are normalized to {"success": false, "error": {...}}.
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response") if renderer_context else None
        already_wrapped = isinstance(data, dict) and isinstance(data.get("success"), bool)
        status_code = getattr(response, "status_code", 200) if response is not None else 200

        if already_wrapped:
            wrapped = data
        elif response is not None and response.exception:
            wrapped = data
        elif status_code >= 400:
            if isinstance(data, dict) and "detail" in data and len(data) == 1:
                message = str(data["detail"])
                details = data
            elif isinstance(data, list):
                message = "; ".join(str(d) for d in data)
                details = data
            elif isinstance(data, dict):
                message = str(data.get("detail") or data.get("message") or "Request failed.")
                details = data
            else:
                message = str(data) if data is not None else "Request failed."
                details = data
            wrapped = {
                "success": False,
                "error": {
                    "code": "error",
                    "message": message,
                    "details": details,
                },
            }
        else:
            wrapped = {"success": True, "data": data}
        return super().render(wrapped, accepted_media_type, renderer_context)
