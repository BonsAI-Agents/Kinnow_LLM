# Decisions on disputed legal points

A short log of points where sources disagreed and who settled them, so the training data can be traced to a decision.

| Date | Point | Decision | Who | Where it is used |
|---|---|---|---|---|
| 21 Nov 2026 | Interest under Section 50(3) CGST (ITC wrongly availed and utilised) | **18% a year**, same as Section 50(1). Tejas cites Notification 14/2022-CT and says the Act's 24% is only the ceiling | Owner | Training data, generator template, four golden questions, fact check |
| 22 Nov 2026 | Same point | Owner states the **CA approved 18%**. No written CA confirmation is stored in this repo; add the notification number or the CA's note here when you have it | Owner (reporting the CA) | Pending-CA list emptied in `scripts/merge_tejas_data.py` |
| 24 Nov 2026 | Post-supply discounts, Section 15(3)(b) CGST | Finance Act 2026 sections 153-155 (Notification 03/2026-CT, 26 Oct 2026) removed the prior-agreement and invoice-link conditions **from 1 Nov 2026**. Sources differ on whether the recipient must still reverse ITC. Nine training rows that state the old conditions as the test are **held** until rewritten with the date | Web research (secondary sources, the amended text was not read) | `HOLD` in `scripts/merge_tejas_data.py`; golden question `post_supply_discount_no_agreement` still expects the old answer and is now out of date |
| 24 Nov 2026 | Goods transport agency (GTA) rate options | Since 22 Sep 2025: **5% without ITC or 18% with full ITC**. The 12% option no longer exists. Our first brief said 5% or 12% and was wrong | Web research (several secondary sources agree) | Batches 3 and later; new-batch prompt |
| 24 Nov 2026 | New form names, Income-tax Act 2025 (from 1 Apr 2026) | Form 16 -> 130, 16A -> 131, 16B-16E -> 132, 24Q -> 138, 26Q -> 140, 27Q -> 144, 26QB/QC/QD/QE -> 141, 12B -> 122, 12BA -> 123, 12BB -> 124. Form 10E: not found | Web research (secondary sources) | New-batch prompt, glossary |
| 24 Nov 2026 | Maharashtra professional tax | Men: nil to Rs 7,500, Rs 175 for Rs 7,501-10,000, Rs 200 above, Rs 300 in February (Rs 2,500 a year). Women's threshold of Rs 25,000 is reported by one source only: **not used** | Web research; official MahaGST schedule lists the men's slabs | No training row uses professional tax |
| 24 Nov 2026 | Meal vouchers | Rs 50 per meal up to FY 2025-26, Rs 200 from tax year 2026-27 (Rule 15(5)(a), Income-tax Rules 2026). Whether the new regime gets it: sources disagree, **not stated either way** | Web research | `OVERRIDES` in `scripts/merge_tejas_data.py` |
| 24 Nov 2026 | 78 rows marked "check" in Tejas's batches 1-9 | Each was researched: 18 kept, 29 fixed, 31 dropped (unsettled or unsourced). Eight agent verdicts were overridden to drop because they rested on memory or an unconfirmed figure | Web research | `data/tejas/new_v3/checked_rows_verified.jsonl` and `checked_rows_dropped.jsonl` (with a reason for each drop) |

## Notes
- Independent web checks on 21 and 22 Nov 2026 found secondary sources stating 24% for Section 50(3) and described
  Notification 14/2022-CT as the one that introduced Rule 88B (the calculation method). The official notification text
  was not read. If a future review disagrees with 18%, the places to change are listed in the last column above, then retrain.
- The 24 Nov 2026 entries come from tax blogs, advisory sites and law-firm updates, not from the gazette or the official portals.
  Treat them as a good first answer and have a CA confirm before the data is used for anything outside this project.

## Still open
- Women's professional tax threshold in Maharashtra, and Karnataka slabs (no training row uses them).
- Whether the new tax regime allows the meal-voucher exemption.
- Whether the recipient must still reverse ITC on a post-supply discount after 1 Nov 2026, and which date decides it (supply or credit note).
- Form 10E's new name.
- A written CA note for the Section 50(3) rate.
