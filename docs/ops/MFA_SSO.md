# MFA / SSO decision (4.3)

> **Superseded, 2026-10-24.** Two-step sign-in is built: an authenticator app (TOTP) plus hashed
> recovery codes (`backend/accounts/mfa_service.py`, Security page in the app). Production requires
> it for Owners, Accountants and anyone who can post journals (`MFA_ENFORCE_FOR_MONEY_ROLES`).
> The text below is the original pre-freeze decision, kept for history.

Freeze **does not** require a TOTP product. A26 is OTP-SMS (optional) + password.

| Option | Freeze | LLM may |
|---|---|---|
| Password + optional SMS OTP | In (A26, C6) | Tests, `OTP_DEBUG_ECHO=0` guards |
| Screenshare-only support | Default | Guard that no impersonation API exists (done) |
| TOTP + hashed recovery | Split, post-freeze unless founder asks | Decision doc only — **this file** |
| SSO / OIDC for customer login | Out | Do not implement |

**Recommendation until founder enrolls a device:** keep password (+ SMS OTP on hosts with `SMS_PROVIDER`). Do not ship a half-MFA UX.
