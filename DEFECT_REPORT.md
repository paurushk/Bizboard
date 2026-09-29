# Defect report

Cycle 2026-09-27. Confirmed defects only. Earlier root drafts that used non-canonical workflow ids are withdrawn.

No confirmed product defect in this cycle.

| Check | Result |
|---|---|
| Serial lookup by exact number, including a unit never sold | Product did not filter `serial_number` on the list, and sales staff could not read serials. Both are now the behaviour under test. Not left as an open gap. |
| Onboarding "<= 3 steps" | The product's blocking path is four steps. The journey text was wrong. The test pins four. Payments stay optional. |
| I2, I3, I4, I5 | P95 / elapsed within the Phase 0 targets on this machine, invariant sweep on |
| I1 | Not measured. The Playwright spec does not assert 100ms. Recorded as unmeasured, not as a breach |
| Query counts on four desk lists | Flat at 20 vs 40 rows within + 2 |

Severity rubric used if a defect had been filed: P0–P3 / UX / SUGG from `docs/reviews/DEEP_LINE_REVIEW_2026-09-02.md`.
