"""Outbound integrations discovered from code — freeze-safe inventory.

Each row is a real adapter or HTTP client in the tree. ``settings_keys`` must
exist on django.conf.settings (possibly empty). Fallback is what operators
do when the vendor is down. money_path True means a failure must not Complete
a document half-way.
"""

from __future__ import annotations

INTEGRATIONS: tuple[dict, ...] = (
    {
        "name": "razorpay_subscriptions",
        "settings_keys": ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"),
        "sandbox": True,
        "fallback": "Stub checkout in non-prod; write-block via subscription status",
        "money_path": True,
    },
    {
        "name": "razorpay_collections",
        "settings_keys": ("SANDBOX_WEBHOOK_SECRET",),
        "sandbox": True,
        "fallback": "Disable online collect; take cash/UPI offline",
        "money_path": True,
    },
    {
        "name": "cashfree_collections",
        "settings_keys": ("CASHFREE_APP_ID", "CASHFREE_SECRET_KEY", "CASHFREE_WEBHOOK_SECRET"),
        "sandbox": True,
        "fallback": "Disable online collect; take cash/UPI offline",
        "money_path": True,
    },
    {
        "name": "payu_collections",
        "settings_keys": ("PAYU_MERCHANT_KEY", "PAYU_MERCHANT_SALT", "SANDBOX_WEBHOOK_SECRET"),
        "sandbox": True,
        "fallback": "Disable online collect; take cash/UPI offline",
        "money_path": True,
    },
    {
        "name": "smtp_email",
        "settings_keys": ("DEFAULT_FROM_EMAIL",),
        "sandbox": True,
        "fallback": "Log send failure; password-reset still returns uniform 200",
        "money_path": False,
    },
    {
        "name": "sms_otp",
        "settings_keys": ("SMS_PROVIDER",),
        "sandbox": True,
        "fallback": "Password login; OTP unavailable when SMS_PROVIDER unset",
        "money_path": False,
    },
    {
        "name": "sentry",
        "settings_keys": ("SENTRY_DSN",),
        "sandbox": True,
        "fallback": "Structured logs only",
        "money_path": False,
    },
    {
        "name": "gsp_einvoice",
        "settings_keys": ("GSP_LIVE_ENABLED",),
        "sandbox": True,
        "fallback": "Preview only; GSP_LIVE_ENABLED=0 in freeze",
        "money_path": True,
    },
    {
        "name": "tally",
        "settings_keys": ("ENABLE_TALLY",),
        "sandbox": True,
        "fallback": "Export dump; live sync dark in freeze",
        "money_path": False,
    },
    {
        "name": "whatsapp_cloud",
        "settings_keys": ("ENABLE_WHATSAPP_CLOUD",),
        "sandbox": True,
        "fallback": "wa.me share-link; Cloud send dark in freeze",
        "money_path": False,
    },
)
