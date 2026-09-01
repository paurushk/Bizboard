import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
print("import django", flush=True)
import django

print("setup", flush=True)
django.setup()
print("django ok", flush=True)

from config.settings import (
    _assert_allowed_hosts,
    _is_local_allowed_host,
    _parse_debug_flag,
)

print("star local?", _is_local_allowed_host("*"), flush=True)
print("debug true?", _parse_debug_flag("true"), flush=True)
_assert_allowed_hosts(["localhost"], "production")
print("helpers ok", flush=True)
