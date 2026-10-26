# Subprocessors (10.8)

Inventory is derived from `backend/core/integration_inventory.py`. Counsel
fills DPAs. This list is **not** a legal DPA.

| Code name | Typical vendor | Money path | Freeze |
|---|---|---|---|
| razorpay_subscriptions | Razorpay | yes | SaaS billing |
| razorpay_collections | Razorpay | yes | A25 sandbox |
| cashfree_collections | Cashfree | yes | A25 sandbox |
| payu_collections | PayU | yes | A25 sandbox |
| smtp_email | Resend (SMTP relay) | no | password reset |
| sms_otp | MSG91 / Twilio | no | A26; off if unset |
| sentry | Sentry, or self-hosted GlitchTip (`GLITCHTIP.md`; then not a subprocessor) | no | errors |
| gsp_einvoice | GSP / NIC | yes | live submit dark (`GSP_LIVE_ENABLED=0`) |
| tally | Tally | no | Table B dark |
| whatsapp_cloud | Meta Cloud | no | Table B dark; `wa.me` share-link stays |

**Not in `integration_inventory.py` but processing personal data when switched on** (added
2026-10-25, WP-3; contract checks in `docs/legal/drafts/VENDOR_CONTRACT_CHECKLIST.md`):

| Code name | Typical vendor | Money path | Freeze |
|---|---|---|---|
| llm_provider (`LLM_PROVIDER`) | OpenAI (default), Anthropic, DeepSeek | no | Owner-switched AI features only |
| google_signin | Google | no | "Sign in with Google", if enabled |
| edge_and_turnstile | Cloudflare | no | Edge/TLS if used; Turnstile at sign-up |
| telegram_alerts | Telegram | no | Only when a user links Telegram |
| identity_check (`IDENTITY_PROVIDER`) | PAN / Udyam verification provider | no | Off unless configured |
| account_aggregator (`FIU_BASE_URL`) | FIU / AA gateway | no | Off unless configured |
| hosting | Host (region not chosen, D-18) and backup storage account | no | Always, once hosted |

Region / residency commitments are Human. Flip a dark flag only via
`docs/ops/FREEZE_EXCEPTION.md`.
