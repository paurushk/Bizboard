# Status communication (11.7)

## Public status page (BB-128)

`https://<app domain>/status/` shows whether **Bizboard app** and **Saving and loading data** are up,
checked every minute by the error tracker's uptime monitors (`docs/ops/GLITCHTIP.md`). The app's
nginx serves only that one read-only page from GlitchTip (GET only, its own strict security policy,
no cookies); the tracker itself stays private. With error tracking off, the path answers 503 and the
app is unaffected. Link it from the website footer and the in-app Help page.

The page shows up/down only. For an incident, post the update below in the same places (WhatsApp
broadcast to pilot owners, email) and add a line to the in-app announcement banner.

## Incident update

**Incident update template**

- Detected (IST):
- Sev:
- What users see:
- What not to do (do not re-complete; do not pay twice):
- Next update by:
- Workaround:

Post in the same channel as uptime alerts. Do not claim GST portal filing in an incident banner.
