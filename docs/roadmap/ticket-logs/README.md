# Ticket logs (append-only)

Cursor / Cloud agents: **do not** edit the Progress log table in
`WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md`. Create or append:

`docs/roadmap/ticket-logs/<TICKET-ID>.md`

Example filename: `W0-02.md`, `A-06.md`, `P0-01.md`.

Each line:

```
YYYY-MM-DD | DONE|PARTIAL|BLOCKED | <short-sha> | <one sentence>
```

Integrator (PM until §0.5 names someone) merges branches; this folder avoids
markdown merge conflicts on the plan file.
