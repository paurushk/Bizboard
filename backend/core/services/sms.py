"""SMS provider abstraction — MSG91/Twilio-ready; console stub in development."""

from django.conf import settings

from core.exceptions import BusinessRuleError

# Only these values have an actual implementation below (console print).
# Real gateway integrations (MSG91/Twilio) are not wired up yet — RequestOtpView
# additionally blocks OTP requests outside DEBUG so this never silently
# reports "OTP sent" without the SMS actually being deliverable (BUG-102).
_IMPLEMENTED_PROVIDERS = {"", "console", "stub"}


class SmsProvider:
    @staticmethod
    def send_otp(phone: str, code: str) -> None:
        provider = (getattr(settings, "SMS_PROVIDER", "") or "").strip().lower()
        if provider in _IMPLEMENTED_PROVIDERS:
            # Dev / unset: log only; never rely on this in production.
            print(f"[SmsProvider] OTP for {phone}: {code}")
            return
        raise BusinessRuleError(
            f"SMS provider '{provider}' is not implemented. Wire a real gateway "
            "(MSG91/Twilio) in core.services.sms before enabling it."
        )
