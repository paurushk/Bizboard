from rest_framework.routers import DefaultRouter as _DefaultRouter


class DefaultRouter(_DefaultRouter):
    """DefaultRouter with format-suffix patterns (``/foo.json``) disabled.

    The project never serves or requests suffixed URLs; suffix patterns
    only cost us a Django `RemovedInDjango60Warning` per router beyond the
    first, since DRF re-registers the same URL converter name every time
    `include_format_suffixes` is True.
    """

    include_format_suffixes = False
