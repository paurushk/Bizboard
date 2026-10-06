"""Drop websocket connections when a user is deactivated.

The channel layer is optional. When it is not installed, deactivation still
revokes tokens and this function does nothing.
"""

from __future__ import annotations


def drop_user_sockets(user) -> bool:
    try:
        from channels.layers import get_channel_layer
    except Exception:
        return False
    layer = get_channel_layer()
    if layer is None:
        return False
    group = f"user-{getattr(user, 'pk', '')}"
    try:
        from asgiref.sync import async_to_sync

        async_to_sync(layer.group_send)(group, {"type": "disconnect.user"})
    except Exception:
        return False
    return True
