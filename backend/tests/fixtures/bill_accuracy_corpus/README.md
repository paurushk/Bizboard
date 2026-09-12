# LLM bill-extraction accuracy corpus (QOS-0015)

Empty on purpose — this is the harness shell, not the benchmark itself. A
synthetic/rendered "bill" would be trivially easy for a vision model to read
and would measure nothing about real-world accuracy, so no fixtures are
faked in here. Drop real (ideally anonymised — redact GSTIN/names of anyone
who didn't consent to being in a test fixture) purchase-bill photos here to
activate `tests/accuracy/test_llm_bill_extraction_accuracy.py`.

## Format

One case = one image + one expected-fields JSON, same base name:

```
tests/fixtures/bill_accuracy_corpus/
  case-001.jpg
  case-001.json
  case-002.png
  case-002.json
  ...
```

`case-NNN.json` — the ground truth to score the extraction against, same
shape `core.services.llm.extract_purchase_bill` returns:

```json
{
  "supplier_name": "VTC Tradewings Pvt Ltd",
  "supplier_gstin": "09AAPCS3897R1ZX",
  "bill_number": "VTAGR-26-1038635",
  "bill_date": "2026-06-11",
  "lines": [
    {"name": "Olay NA IGF 40gm", "quantity": "3", "unit_price": "140.50", "gst_rate": "18"}
  ]
}
```

Only the keys you actually want scored need to be present — the test skips
any key missing from a case's JSON rather than penalising it.

## Running

With no cases present, the test SKIPS with an explanatory message — it does
not fail the suite. Once real cases exist:

```bash
cd backend
OPENAI_API_KEY=... pytest tests/accuracy/test_llm_bill_extraction_accuracy.py -m llm_accuracy -v
```

This calls the real configured LLM provider (real API cost, no network
mocking) — it is not part of the default `pytest` run; see the
`llm_accuracy` marker in `pytest.ini`. `ACCURACY_FLOOR` at the top of the
test file is the pass/fail bar once you have enough cases to trust it —
leave it conservative until the corpus has real size.
