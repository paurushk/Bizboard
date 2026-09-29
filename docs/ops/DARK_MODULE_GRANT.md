# Dark module grant

`ENABLE_CRM`, `ENABLE_MANUFACTURING`, and `ENABLE_PAYROLL` are dark modules. The environment flag is the deployment ceiling only when the company has no subscription. A subscribed plan that does not name the module leaves it off. Writing `{"ENABLE_CRM": true}` into company JSON does not turn it on while a plan omits it.

## Who may grant

A deployment operator, not a pack confirm of `retail` or `trade`, and not a tenant editing their own JSON.

- CRM for a named pilot: confirm the `insurance` pack, or set the company's plan `modules` to include `"ENABLE_CRM": true`. The insurance pack is the only pack that sets `pack_grant` to `insurance`, which is what turns CRM on together with referrals, tickets, and complaints.
- Manufacturing and payroll: set the plan module explicitly. Do not add them to `PACKS`. `HELD_PACKS` still contains `manufacturing`. `propose_pack` never returns it.

## How to turn one off

Remove the key from the plan modules, and remove `pack_grant` if the insurance pack had set it. Confirming retail or trade never writes these keys.
