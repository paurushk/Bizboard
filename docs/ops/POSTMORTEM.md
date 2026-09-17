# Postmortem template (11.9)

Copy this file into the incident ticket. Human owns customer-facing wording.

- **Incident:**
- **Sev:** 1 / 2 / 3 / 4
- **Start / detect / mitigate / resolve (IST):**
- **Image tag / migration head / backup used:**
- **What customers saw:**
- **What they were told not to do:**
- **Trigger:**
- **Detection gap (which alert fired / failed):**
- **Why the first fix was or was not a rollback:**
- **Data integrity:** stock / AR / AP / GL / SaaS subscription checked? (link invariant command)
- **Tenant isolation:** any cross-company evidence?
- **Action items** (owner, date, freeze-safe?):
  - [ ]
- **What we will not do:** feature work that expands freeze Table B, invent ToS copy, or enable prod RLS to “paper over” an app-layer bug.
