"""SMS provider abstraction — MSG91/Twilio-ready; console stub in development."""

from django.conf import settings


class SmsProvider:
    @staticmethod
    def send_otp(phone: str, code: str) -> None:
        provider = (getattr(settings, "SMS_PROVIDER", "") or "").strip().lower()
        if not provider or provider in ("console", "stub"):
            # Dev / unset: log only; never rely on this in production.
            print(f"[SmsProvider] OTP for {phone}: {code}")
            return
        # Production providers plug in here (MSG91 / Twilio).
        # Until configured, RequestOtpView blocks non-DEBUG requests.
        print(f"[SmsProvider:{provider}] OTP for {phone}: {code}")
