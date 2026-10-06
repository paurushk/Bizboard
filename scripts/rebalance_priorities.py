# -*- coding: utf-8 -*-
"""
Rebalance priorities from the task action only.

P0 is limited to actions that name a statutory control, credit-limit block, or
ledger-integrity check. P3 is limited to polish and speculative features.
Owner reports such as margin, valuation, and dead stock keep their authored
priority. Notes are not scanned: words like "atomic" in a note are not the task.
"""

import csv
import sys
import os

sys.path.insert(0, os.path.abspath('.'))

# Priority is judged from the task action only. Notes and outcomes mention
# implementation words ("atomic", "credit limit") that are not the task itself.
# Core owner reports (margin, valuation, dead stock, store comparison) stay at
# their authored priority. They are not polish items.
P3_ACTION_PHRASES = [
    "Conversational AI Assistant",
    "WhatsApp Conversational Khata Bot",
    "negotiation bot",
    "churn prediction",
    "Dead-Stock Liquidation Assistant",
    "Outdoor Sunlight Mode",
    "Customer-facing Pole Display",
    "White-label branding",
    "In-app customer feedback",
    "garbage collection",
    "database index bloat",
    "slow-query telemetry",
    "Voice message and infographic",
    "Anti-Profiteering",
    "Section 128A",
    "dormant user account",
    "Graceful degradation",
    "Directions API",
    "sound feedback",
    "Privacy Mask",
    "photo tamper detection",
]

P0_ACTION_PHRASES = [
    "Rule 46",
    "Rule 48",
    "Rule 11(g)",
    "Row-Level Security",
    "zero-sum",
    "immutable audit",
    "E-Invoice",
    "E-Way Bill",
    "expired-stock",
    "expired stock",
    "Section 16(2)",
    "Section 16(4)",
    "Section 17(5)",
    "Section 34",
    "Section 50",
    "Drug License",
    "FSSAI",
    "TOTP",
    "token revocation",
    "credit limit",
    "cheque dishonoured",
    "bounced cheque",
]


def refine_task_priority(row):
    action = (row[4] or "") if len(row) > 4 else ""
    current_prio = row[9]
    text = action.lower()

    for phrase in P3_ACTION_PHRASES:
        if phrase.lower() in text:
            return "P3"

    for phrase in P0_ACTION_PHRASES:
        if phrase.lower() in text:
            return "P0"

    return current_prio

def main():
    import scripts.build_product_task_universe as bptu

    csv_path = "Bizboard_Product_Task_Universe_Master.csv"
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        rows = list(reader)

    updated_rows = []
    p_dist = {}
    for r in rows:
        new_p = refine_task_priority(r)
        r[9] = new_p
        p_dist[new_p] = p_dist.get(new_p, 0) + 1
        updated_rows.append(r)

    print("Refined Priority Distribution across 715 tasks:", p_dist)

    # Re-save master files
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(updated_rows)

    # Re-build Excel
    bptu.main()
    print("Master Excel workbook regenerated with refined priority distribution.")

if __name__ == "__main__":
    main()
