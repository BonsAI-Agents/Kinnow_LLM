# Decisions on disputed legal points

A short log of points where sources disagreed and who settled them, so the training data can be traced to a decision.

| Date | Point | Decision | Who | Where it is used |
|---|---|---|---|---|
| 21 Nov 2026 | Interest under Section 50(3) CGST (ITC wrongly availed and utilised) | **18% a year**, same as Section 50(1). Tejas cites Notification 14/2022-CT and says the Act's 24% is only the ceiling | Owner | Training data, generator template, four golden questions, fact check |
| 22 Nov 2026 | Same point | Owner states the **CA approved 18%**. No written CA confirmation is stored in this repo; add the notification number or the CA's note here when you have it | Owner (reporting the CA) | Pending-CA list emptied in `scripts/merge_tejas_data.py` |

## Notes
- Independent web checks on 21 and 22 Nov 2026 found secondary sources stating 24% for Section 50(3) and described
  Notification 14/2022-CT as the one that introduced Rule 88B (the calculation method). The official notification text
  was not read. If a future review disagrees with 18%, the places to change are listed in the last column above, then retrain.

## Still open
- Maharashtra professional tax slabs (no training row uses them).
- Whether the new tax regime allows the meal-voucher exemption (the row was removed from the data).
