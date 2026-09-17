# Beta archetype checklist (15.1)

Filter recruits against `docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md`. This is
not a signed Go/No-Go. Execution for the lead cohort is
[`ARCH03_PILOT_RUNBOOK.md`](ARCH03_PILOT_RUNBOOK.md).

## Lead — ARCH-03 Semi-wholesaler (B2B credit)

Must be **yes** before onboarding (personas §13 guardrails):

- [ ] Single legal GSTIN (inter-state IGST sales ok; no multi-registration)
- [ ] Bill-accompanied inwarding (no required GRN / 3-way match)
- [ ] Offline GSTR-1 / 3B worksheets; CA files on the portal
- [ ] IRN / e-way generated outside BizBoard if required; numbers recorded
- [ ] Turnover band under the e-invoice threshold used for this cohort
- [ ] Desktop + A4 printer; one practicing CA for month-end
- [ ] Stated limitations: no FA, no BoE landed cost, no GSTR screens, no
      payroll/CRM/manufacturing/Tally live

## Parallel — ARCH-01 counter retail (POS)

- [ ] Counter POS in freeze (A23); no manufacturing floor
- [ ] Cash / UPI at counter; credit is not the primary loop
- [ ] H-02 speed hypothesis is Human-scored, not an LLM claim

## Conditional — ARCH-04 multi-godown

- [ ] Stock transfer between godowns is enough; no bonded warehouse / BoE
- [ ] Same single GSTIN as ARCH-03

## Out of this freeze beta

- ARCH-02 composition (commercially deprioritized)
- ARCH-05 pharma/food statutory forms (`ENABLE_ARCH05_STATUTORY_FORMS` default off)
- ARCH-06 serial/IMEI as the *primary* loop (serial exists; do not recruit on it)
- ARCH-07 project/service milestone billing as the *primary* loop
- Import / Bill of Entry landed cost (D10)
- Fixed assets + depreciation (D6)
- Anyone who needs live GSTN filing or NIC IRN from BizBoard

Do not tick a box from this file in a go-meeting. Copy the yes/no into
`GO_NO_GO.md` with a Human name and date.
