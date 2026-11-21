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
| GST interest | 18% under Sec 50(1); **18% under Sec 50(3)** (Notification 14/2022-CT, from 1 Jul 2017; the Act's 24% is only the ceiling). Fixed in the 500 rows on 21 Nov 2026 | current | CBIC notification |
| E-invoice | Mandatory above ₹5 crore AATO; 30-day IRP reporting limit for AATO ≥ ₹10 crore | 1 Apr 2025 | GSTN advisory |
| GST TDS | 2% on government contracts above ₹2.5 lakh | current | Sec 51 CGST Act |
| Composition | ₹1.5 crore (₹50 lakh services); 1% / 5% / 6% | current | Sec 10 CGST Act |
| Income tax | Income-tax Act, 2025 replaces 1961 Act. Salary TDS under Sec 392; other TDS in Sec 393 tables | 1 Apr 2026 | Income-tax Act, 2025 and Rules |
| Income tax | Forms: 130 (salary TDS certificate, ex-Form 16), 138 (quarterly salary TDS, ex-24Q), also 131/140/144/168 | Tax year 2026-27 | CBDT form notifications |
| Income tax | TDS deposit by 7th; March by 30 April. Quarterly statements 31 Jul / 31 Oct / 31 Jan / 31 May. No-PAN 20% (5% for goods) | 1 Apr 2026 | Same |
| Income tax | New-regime slabs, ₹75,000 standard deduction, 87A rebate to ₹12 lakh: stated for FY 2025-26 only | FY 2025-26 | Finance Act 2025; check for 2026-27 |
| Income tax | Meal vouchers: row removed. FY 2025-26 ₹50 per meal (old regime only); from tax year 2026-27 the Income-tax Rules, 2026 allow ₹200 per meal, and whether the new regime gets it is disputed | — | CA to confirm |
| EPF | Wage ceiling ₹25,000 per month (was ₹15,000) | 17 Sep 2026, S.O. 5109(E) | EPFO notification |
| EPF | 10% rate for establishments with fewer than 20 employees | current | EPF Act |
| ESI | Ceiling ₹21,000; 0.75% employee, 3.25% employer | current | ESIC |
| Labour codes | In force; wages definition (50% rule), fixed-term gratuity after 1 year, overtime at 2x, full and final settlement within 2 working days | 21 Nov 2025 | Code on Wages; Code on Social Security; state rules |
| Professional tax | Not used in any row. Secondary sources say: men ₹175 for ₹7,501-10,000, ₹200 above ₹10,000; women nil up to ₹25,000; ₹300 in February; ₹2,500 a year | — | CA to confirm |

## A2. Added with the 89 worked-example rows (21 Nov 2026)

| Claim | Check against |
|---|---|
| Sec 156 marginal relief caps tax at income above ₹12 lakh; Sec 202 = new regime default | Income-tax Act, 2025 |
| Sec 157 arrears relief claimed in Form 39 (ex-10E) | CBDT forms |
| Sec 393 contractor TDS: ₹30,000 single / ₹1,00,000 aggregate, 1%/2%; GST excluded from the base when shown separately | Sec 393 tables; CBDT circular carry-over |
| EPF Scheme para 2(f) excluded employee and para 26(6) higher-wage option, read with the ₹25,000 ceiling | EPFO |
| Code on Wages Sec 14 (OT 2x), Sec 17(2) (two working days), Sec 26 (bonus: ₹21,000 eligibility, ₹7,000 or minimum wage, 30 days) | Code on Wages, 2019 |
| Code on Social Security Sec 53 (gratuity, >6 months rounds up, fixed-term 1 year), Sec 2(88) wages, ₹20 lakh ceiling | Code on Social Security, 2020 |
| ESI stays for the contribution period after wages cross ₹21,000 | ESIC |
| Rule 37 not applicable to RCM and Schedule I supplies; Rule 42 no-turnover rule; Rule 43 60 months; Rule 86B 1% cash; Rule 138 exempt-goods exclusion and validity | CGST Rules |
| Sec 16(4) debit-note date rule (Finance Act 2022); B2C Large limit ₹1 lakh; GST TCS 0.5% from 10 Jul 2024; late fee ₹50/day as notified | CGST Act / notifications |
| MSMED Act Sec 15 (45 days) and Sec 16 (3x bank rate, monthly compounding) | MSMED Act, 2006 |

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
