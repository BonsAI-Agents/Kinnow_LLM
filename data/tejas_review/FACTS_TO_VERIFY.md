# Kinnow training set: facts to verify before training

Prepared 19 Nov 2026. These are the claims in `kinnow_sft_500.jsonl` and `kinnow_dpo_pairs.jsonl` that change over time or carry the most risk if wrong. Get a CA to check the regulatory list and a product owner to check the Kinnow list. If anything changes, fix the rows and retrain. Do not rely on the model weights to stay current.

## A. Regulatory (India): changes recently

| Area | Claim used in the data | Effective | Check against |
|---|---|---|---|
| GST rates | Main slabs 5% and 18%, plus 40% for luxury and sin goods. 12% and 28% removed | 22 Sep 2025 | CBIC rate notifications (GST 2.0) |
| GST rates | Individual life and health insurance exempt; group policies 18% | 22 Sep 2025 | Same |
| GST rates | UHT milk, paneer, Indian breads nil. Small cars, ACs, TVs, cement 18%. Soaps, many medicines 5%. Some stationery exempt | 22 Sep 2025 | Same; check each item against its HSN |
| GST rates | Hotel rooms up to ₹7,500 a night at 5% without ITC | 22 Sep 2025 | Same |
| GST rates | Admission to IPL-type events 40%; other recognised sporting events 18%; tickets up to ₹500 exempt | 22 Sep 2025 | Same |
| Cess | Compensation cess discontinued except on tobacco | 22 Sep 2025 | Same |
| GST returns | GSTR-3B liability hard-locked from GSTR-1/1A | July 2025 tax period | GSTN advisories |
| GST returns | IMS accept / reject / pending; no action counts as accepted | Oct 2024 onward | GSTN advisories |
| GST returns | GSTR-1 on 11th (QRMP 13th), GSTR-3B on 20th (QRMP 22nd/24th), GSTR-2B on 14th, GSTR-7 on 10th | current | GST portal |
| GST interest | 18% under Sec 50(1); 24% under Sec 50(3) for ITC wrongly availed and used | current | CGST Act |
| E-invoice | Mandatory above ₹5 crore AATO; 30-day IRP reporting limit for AATO ≥ ₹10 crore | 1 Apr 2025 | GSTN advisory |
| GST TDS | 2% on government contracts above ₹2.5 lakh | current | Sec 51 CGST Act |
| Composition | ₹1.5 crore (₹50 lakh services); 1% / 5% / 6% | current | Sec 10 CGST Act |
| Income tax | Income-tax Act, 2025 replaces 1961 Act. Salary TDS under Sec 392; other TDS in Sec 393 tables | 1 Apr 2026 | Income-tax Act, 2025 and Rules |
| Income tax | Forms: 130 (salary TDS certificate, ex-Form 16), 138 (quarterly salary TDS, ex-24Q), also 131/140/144/168 | Tax year 2026-27 | CBDT form notifications |
| Income tax | TDS deposit by 7th; March by 30 April. Quarterly statements 31 Jul / 31 Oct / 31 Jan / 31 May. No-PAN 20% (5% for goods) | 1 Apr 2026 | Same |
| Income tax | New-regime slabs, ₹75,000 standard deduction, 87A rebate to ₹12 lakh: stated for FY 2025-26 only | FY 2025-26 | Finance Act 2025; check for 2026-27 |
| Income tax | Meal vouchers exempt up to ₹50 per meal, old regime only | current | Rules |
| EPF | Wage ceiling ₹25,000 per month (was ₹15,000) | 17 Sep 2026, S.O. 5109(E) | EPFO notification |
| EPF | 10% rate for establishments with fewer than 20 employees | current | EPF Act |
| ESI | Ceiling ₹21,000; 0.75% employee, 3.25% employer | current | ESIC |
| Labour codes | In force; wages definition (50% rule), fixed-term gratuity after 1 year, overtime at 2x, full and final settlement within 2 working days | 21 Nov 2025 | Code on Wages; Code on Social Security; state rules |
| Professional tax | Maharashtra slabs as stated | current | State PT Act |

## B. Kinnow product claims (from CLAUDE_AllModules.md, 19 Nov 2026)

Only ACTIVE K-FEAT rows were used. Recheck these if AllModules changes:

- Agents draft; people approve. Agents never post, file or pay on their own.
- The double-entry validator, approval rules and the mismatch detector block filing while mismatches remain.
- The duplicate detector suggests duplicate parties and never merges on its own.
- Tally bridge is free on every plan; imports chart of accounts, opening balances, opening stock and invoices.
- SAP Ariba connector (cXML: suppliers, POs, invoices).
- Pharma stock: lots with expiry, expiry watchdog, FEFO, expiry return-claim pack.
- GSP direct filing is pilot-gated; ZATCA is framework-only. The rows say so; update them when either goes live.
- Veil, Ask, credits, period close, P2P, O2C, inventory, warehouse, transport, reports and payments as described in the ERP rows.

## C. Data rules checked

- No customer names or customer data in any row (automatic check against tenant names).
- No secrets, no personal data, no "Jev".
- All rows written from public law and the AllModules feature catalogue, not from customer records (KINNOW_RULES R2).
