# Verification report: claims in `FACTS_TO_VERIFY.md`

Researched 19 Nov 2026 by Claude (web search against official and secondary sources). **This is a research
aid, not a CA sign-off.** Almost all links are secondary sources (tax portals, law firms, news). A few are
official (PIB, GST Council press release, Income Tax Department). I did not open the gazette PDFs, so a CA
should confirm anything marked "Needs CA".

Status key: **Confirmed** = several independent sources agree (official source noted where there is one).
**Partly** = the core is right, a detail is unconfirmed. **Conflict** = sources disagree. **Not found** = my
search did not cover it. **Outdated?** = evidence says the data is behind current law.

## Items that need action first

| # | Claim in data | Finding | Action |
|---|---|---|---|
| 1 | Meal vouchers exempt up to Rs 50 per meal, old regime only (1 SFT row) | **Outdated?** The Rs 50 limit is the old Rules 1962 figure. The Income-tax Rules 2026 raise it to Rs 200 per meal from tax year 2026-27. Sources disagree on whether it covers both regimes. | CA to confirm Rule 15(5)(a) of the 2026 Rules; then rewrite the row. |
| 2 | Forms 130/138 replace 16/24Q (SFT + my DPO pairs) | **Confirmed, but date matters.** FY 2025-26 salary TDS still uses the 1961 Act, Section 192, Form 16, Form 24Q. Forms 130/138 apply to tax year 2026-27 (salary paid from 1 Apr 2026). | I already added the date to my DPO pairs. Check Tejas's rows say "from tax year 2026-27". |
| 3 | Interest 24% under Section 50(3) | **Conflict.** Sources disagree whether 24% still applies after the Finance Act 2022 change. | CA to confirm the notified rate. |
| 4 | Maharashtra professional tax slabs | **Conflict.** Men's slabs differ between sources (Rs 7,500 / 10,000 / 175 / 200 vs a threshold of Rs 25,000). One source says the Rs 300 month is March, not February. | CA to check Schedule I of the Maharashtra Act. |
| 5 | No-PAN TDS 20% (5% for goods); EPF 10% rate under 20 employees | **Not found** in my searches. | CA to confirm. |
| 6 | GSTR-2B generated on the 14th; IMS "no action counts as accepted" | **Not found** in my searches. | CA / GST portal check. |
| 7 | Overtime at 2x | **Partly.** Only one source. | CA to check the Code on Wages. |

## A. GST rates (GST 2.0, 22 Sep 2025)

| Claim | Status | Evidence |
|---|---|---|
| Slabs 5% and 18%, plus 40%; 12% and 28% removed | **Confirmed** | [GST Council press release](https://gstcouncil.gov.in/sites/default/files/2025-09/press_release_press_information_bureau.pdf), [PIB document](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/sep/doc202594628401.pdf), [ClearTax](https://cleartax.in/s/56th-gst-council-meet-news), [Tally](https://tallysolutions.com/gst/new-gst-rates-september-2025-business-impact/) |
| Notifications 09/2025 to 17/2025-CT (Rate), dated 17 Sep 2025 | **Confirmed** (one source gives the numbers) | [TaxGuru](https://taxguru.in/goods-and-service-tax/gst-mega-reforms-india-rates-slabs-key-2025.html), [BusinessToday](https://www.businesstoday.in/amp/latest/economy/story/gst-rate-cuts-notified-by-centre-effective-sept-22-companies-prepare-for-simplified-structure-494452-2025-09-17) |
| UHT milk, paneer, Indian breads nil | **Confirmed** | [Tally](https://tallysolutions.com/gst/gst-2-0-reforms-business-impact/), [Taxscan](https://www.taxscan.in/top-stories/key-highlights-of-the-56th-gst-council-meeting-rate-rationalization-trade-facilitation-1432230) |
| Small cars, ACs, TVs, cement 18% | **Confirmed** | [Storyboard18](https://www.storyboard18.com/how-it-works/gst-on-acs-cement-tvs-and-cars-reduced-tobacco-and-aerated-drinks-face-40-levy-80228.htm), [Tally FAQ](https://tallysolutions.com/gst/new-gst-rates-2025-key-changes-and-faqs) |
| Individual life and health insurance exempt; group 18% | **Confirmed** (individual); group rate **not checked** | [Tally](https://tallysolutions.com/gst/gst-2-0-reforms-business-impact/) |
| Hotel rooms up to Rs 7,500 at 5% without ITC | **Confirmed** (5%); "without ITC" **not checked** | [Tally](https://tallysolutions.com/gst/gst-2-0-reforms-business-impact/) |
| IPL-type events 40% | **Confirmed**; "other sporting events 18%, tickets up to Rs 500 exempt" **Partly** | [Tally](https://tallysolutions.com/gst/gst-2-0-reforms-business-impact/) |
| Soaps, many medicines 5%; some stationery exempt | **Not checked item by item** | CA to check each against its HSN |
| Compensation cess discontinued except tobacco | **Confirmed**, with a nuance: tobacco keeps its old rate and cess until the cess loans are repaid | [Alvarez & Marsal](https://www.alvarezandmarsal.com/node/86886), [Storyboard18](https://www.storyboard18.com/how-it-works/gst-on-acs-cement-tvs-and-cars-reduced-tobacco-and-aerated-drinks-face-40-levy-80228.htm) |

## B. GST returns, e-invoice, interest, TDS, composition

| Claim | Status | Evidence |
|---|---|---|
| GSTR-3B liability hard-locked from GSTR-1/1A, from the July 2025 period | **Confirmed** | [Taxscan](https://www.taxscan.in/breaking-gstn-issues-warning-on-hard-locking-of-auto-populated-values-in-gstr-3b/447890), [The Munim](https://themunim.com/blog/gstr-3b-autofill-facility/) |
| IMS: accept / reject / pending | **Confirmed**; "no action = accepted" **Not found** | [The Munim](https://themunim.com/blog/gstr-3b-autofill-facility/) |
| GSTR-1 on 11th, GSTR-3B on 20th, QRMP 22nd/24th, GSTR-7 on 10th | **Confirmed** (QRMP GSTR-1 is the 13th) | [ClearTax calendar](https://cleartax.in:443/s/gst-calendar), [Tally](https://tallysolutions.com/gst/gst-return-deadlines/) |
| GSTR-2B on the 14th | **Not found** | |
| Interest 18% under Section 50(1) | **Confirmed** | [ClearTax](https://cleartax.in/s/interest-under-section-50-cgst-act-2017) |
| Interest 24% under Section 50(3) | **Conflict** (see top table) | [ClearTax](https://cleartax.in/s/interest-under-section-50-cgst-act-2017) |
| E-invoice above Rs 5 crore | **Confirmed**, in force since 1 Aug 2023, not 1 Apr 2025 as the date column suggests | [The Tax Corp](https://thetaxcorp.in/article/navigating-the-dual-gst-e-invoicing-thresholds-the-rs-5-crore-mandate-vs-the-30), [Tally](https://tallysolutions.com/accounting/e-invoicing-rules-in-india/) |
| 30-day IRP limit for Rs 10 crore and above, from 1 Apr 2025 | **Confirmed** (GSTN advisory of 5 Nov 2024) | [The Tax Corp](https://thetaxcorp.in/article/navigating-the-dual-gst-e-invoicing-thresholds-the-rs-5-crore-mandate-vs-the-30) |
| GST TDS 2% on government contracts above Rs 2.5 lakh | **Confirmed** (per contract, excluding GST) | [Masters India](https://www.mastersindia.co/blog/gst-tds-guide-rules-section-51/), [TaxGuru](https://taxguru.in/goods-and-service-tax/section-51-gst-act-deduction-tds-specified-persons.html) |
| Composition: Rs 1.5 crore (Rs 50 lakh services); 1% / 5% / 6% | **Confirmed**; special-category states have a Rs 75 lakh goods limit | [Busy](https://busy.in/gst/gst-composition-scheme/), [TaxGuru](https://taxguru.in/goods-and-service-tax/analysis-composition-levy-section-10-cgst-act-2017.html) |

## C. Income tax (Income-tax Act, 2025)

| Claim | Status | Evidence |
|---|---|---|
| 2025 Act replaces 1961 Act from 1 Apr 2026; salary TDS under Section 392; other TDS in Section 393 | **Confirmed** | [TaxGuru](https://taxguru.in/income-tax/income-tax-act-2025-structural-tds-compliance-guide.html), [SKLA](https://skla.in/insights-new-act-tds-changes) |
| Form 130 (ex-Form 16), Form 138 (ex-24Q) | **Confirmed** (one source wrongly lists 143 for 24Q; 143 is TCS) | [TaxGuru Form 130](https://taxguru.in/income-tax/form-130-tds-certificate-salary-replacing-form-16.html), [TDSMAN mapping](https://blog.tdsman.com/2026/06/new-tds-tcs-forms-it-act-2025-mapping-with-old-forms/), [CAclubindia](https://www.caclubindia.com/articles/form-130-income-tax-act-2025-55768.asp) |
| Forms 131 (ex-16A), 140 (ex-26Q), 144, 168 (ex-26AS/AIS) | **Confirmed** | [ClearTax Form 140](https://cleartax.in/s/form-140-income-tax), [Income Tax Dept Form 140 FAQs](https://www.incometaxindia.gov.in/documents/d/guest/form-140-faqs) |
| Quarterly statements 31 Jul / 31 Oct / 31 Jan / 31 May | **Confirmed** | [StudyCafe calendar](https://studycafe.in/tds-and-tcs-due-date-compliance-calendar-for-tax-year-2026-27-419614.html) |
| TDS deposit by the 7th; March by 30 April | **Partly** (one transition guide, tied to the old challan structure) | [StudyCafe](https://studycafe.in/tds-and-tcs-due-date-compliance-calendar-for-tax-year-2026-27-419614.html) |
| New regime: Rs 75,000 standard deduction; rebate to Rs 12 lakh (FY 2025-26) | **Confirmed**; sources say 2026-27 is unchanged | [Axis Max Life](https://www.axismaxlife.com/blog/tax-savings/new-tax-regime-fy-2025-26), [CAclubindia](https://www.caclubindia.com/articles/new-tax-regime-fy-202627-complete-slab-rebate-marginal-relief-reference-56353.asp) |
| Meal vouchers Rs 50, old regime | **Outdated?** (see top table) | [AngelOne](https://www.angelone.in/news/taxation/meal-voucher-tax-rules-50-vs-200-exemption-explained-for-fy-2025-26), [Taxmann](https://www.taxmann.com/post/blog/opinion-meal-voucher-tax-benefit-under-new-tax-regime) |

## D. EPF, ESI, labour codes, professional tax

| Claim | Status | Evidence |
|---|---|---|
| EPF wage ceiling Rs 25,000 from 17 Sep 2026 | **Confirmed** (official) | [PIB](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2313829&reg=48&lang=2), [PIB (EPFO Goa)](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2313790&reg=48&lang=2), [PM India: Cabinet approval](https://www.pmindia.gov.in/en/news_updates/cabinet-approves-enhancement-of-epfo-wage-ceiling-from-rs-15000-to-rs-25000-per-month/) |
| Notification number S.O. 5109(E) | **Partly** (named in one source only) | [Upstox](https://upstox.com/news/personal-finance/latest-updates/epfo-wage-ceiling-hiked-to-25-000-labour-ministry-issues-gazette-notification/article-200466/) |
| ESI ceiling Rs 21,000; 0.75% employee, 3.25% employer | **Confirmed** (one source mentions a proposed rise, not notified) | [ClearTax](https://cleartax.in/s/esic), [Petpooja](https://blog.petpooja.com/finance-compliance/esi-esic-contribution-rate-employer-employee-share/) |
| EPF 10% rate for establishments with under 20 employees | **Not found** | |
| Labour codes in force 21 Nov 2025 | **Confirmed** | [India Briefing](https://www.india-briefing.com/news/india-notifies-all-four-labor-codes-ushering-in-landmark-workforce-reforms-40874.html), [Bar & Bench](https://www.barandbench.com/view-point/labour-codes-key-highlights) |
| Fixed-term gratuity after 1 year | **Confirmed** | [People Matters](https://www.peoplematters.in/news/economy-policy/indias-new-gratuity-rules-2025-what-employers-and-employees-should-know-47753) |
| Full and final settlement within 2 working days | **Confirmed** | [India Briefing](https://www.india-briefing.com/news/india-notifies-all-four-labor-codes-ushering-in-landmark-workforce-reforms-40874.html) |
| Overtime at 2x | **Partly** (one source) | [Bar & Bench](https://www.barandbench.com/view-point/labour-codes-key-highlights) |
| Maharashtra professional tax slabs | **Conflict** (see top table) | [Kredily](https://kredily.com/professional-tax-maharashtra/), [StartupGrantsIndia](https://www.startupgrantsindia.com/hindi/calculators/operations/professional-tax/maharashtra), [Patron](https://www.patronaccounting.com/tools/professional-tax-calculator) |

## E. Kinnow product claims

Cannot be checked from public sources. Only the Kinnow product owner can confirm them (the Tally bridge being free on every plan, ZATCA framework-only, GSP direct filing pilot-gated, the duplicate detector never merging on its own, and the rest of section B).
