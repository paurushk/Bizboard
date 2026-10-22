#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable?"
        ) from exc
    # WP-SC2: shell / dbshell on production need a live break-glass session (core/breakglass.py).
    from core.breakglass import enforce

    enforce(sys.argv)
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
