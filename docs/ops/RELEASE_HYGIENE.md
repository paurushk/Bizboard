# Per-release hygiene (C.4)

For every prod deploy:

1. Git SHA and image digest (`pin_image_digests.sh`)
2. `python scripts/ops/freeze_baseline.py` digest (confirm freeze file unchanged or Human accepted)
3. `showmigrations` heads per app
4. Release notes: `python scripts/ops/release_notes.py <prev> <sha>` — money/tax/stock first; Human edits before customers see them
5. Expand-only? Else `EXPAND_CONTRACT_OK` already shipped
6. After up: `/api/v1/health/?ready=1`, one Complete → PDF, `check_invariants --company <pilot>`
