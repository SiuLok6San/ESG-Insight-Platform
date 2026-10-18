# Evidence re-check worksheet (October 2026)

The AI evidence review (`data/evidence/ai_review.csv`) flagged 17 of the 45 rows: 13 where the cited page
only partly supports the summary, 6 where the AI chose a different category, and 3 where its quote could
not be found on the page (some rows have more than one flag). For each row, the cited page and nearby
pages were re-read on 18 October 2026. Every quote below is verbatim and was checked by
`scripts/verify_quotes.py` against the PDF page it names.

**No category has been changed.** The two project analysts decided each point in the
*Decisions* section at the end on 18 October 2026: every recommendation was accepted, so all 45
categories stay as confirmed, and only one summary (D5) and one note (D6) were edited.

## Summary

| Bank | Indicator | Our category | AI category | AI verdict | Quote found? | Recommendation |
|---|---|---|---|---|---|---|
| ING Group | Emissions disclosure | `scope1_2_3` | `scope1_2_3` | partly supports | yes | keep |
| ING Group | Climate risk management | `strong` | `strong` | partly supports | yes | keep |
| ING Group | Diversity & inclusion | `full` | `partial` | partly supports | yes | keep |
| ING Group | Labour rights | `medium` | `weak` | partly supports | yes | keep |
| ING Group | Customer protection | `building` | `building` | partly supports | yes | keep |
| ING Group | Controversy | `moderate` | `moderate` | partly supports | yes | keep |
| ABN AMRO | Emissions disclosure | `scope1_2_3` | `scope1_2_3` | partly supports | no | keep |
| ABN AMRO | Climate risk management | `strong` | `strong` | partly supports | yes | keep |
| ABN AMRO | Diversity & inclusion | `full` | `partial` | supports | yes | keep |
| ABN AMRO | Labour rights | `strong` | `medium` | partly supports | yes | keep |
| ABN AMRO | Customer protection | `building` | `building` | partly supports | yes | keep |
| Rabobank | Climate transition plan | `science_based` | `science_based` | partly supports | yes | keep |
| Rabobank | Financed emissions | `pcaf_full` | `pcaf_full` | partly supports | yes | keep |
| Rabobank | Climate risk management | `strong` | `full` | partly supports | yes | keep (decision D1) |
| Rabobank | Diversity & inclusion | `full` | `full` | supports | no | keep |
| Rabobank | AML maturity | `mature` | `mature` | supports | no | keep |
| Rabobank | Board independence | `>=50` | `not_disclosed` | supports | yes | keep (decision D2) |

In short: 15 rows hold up once the full evidence is read (often on a neighbouring page, or with a correctly
copied quote), and 2 rows are genuine judgment calls (D1, D2). One summary should be worded closer to the source (D5).

## Row by row

### 1. ING Group - Emissions disclosure (`emission_disclosure` = `scope1_2_3`, cited p. 21)

- **AI flag:** partly supports; AI category `scope1_2_3`; AI quote found on the page.
- **Finding:** The AI only saw p. 21, which gives the own-operations footprint but not financed emissions. The p. 21 footprint already covers Scope 1, 2 and 3 (business travel), which meets `scope1_2_3` on its own. PCAF financed emissions are on pp. 125-126 (quoted in the financed-emissions row).
- **Verified quotes:**
   - p. 21: "In 2025, our total operations footprint (scopes 1, 2 and scope 3 business travel) was 44kt of CO2 emissions"
- **Recommendation:** Keep `scope1_2_3`. No change to summary or notes.

### 2. ING Group - Climate risk management (`risk_management` = `strong`, cited p. 208)

- **AI flag:** partly supports; AI category `strong`; AI quote found on the page.
- **Finding:** p. 208 confirms the transition-risk scorecard, climate stress testing and management through the climate risk appetite. The AI could not find the ESG Risk Committee on p. 208: it is described on p. 102. p. 209 adds that ING sets risk appetite statements (RAS) to limit acceptable ESG risk, without disclosing quantified limits.
- **Verified quotes:**
   - p. 208: "Transition risk scorecard: Used by ING to quantify transition risk with a scorecard approach at client-level."
   - p. 208: "ING continues enhancing its climate stress-testing methodology to assess the impact of climate risks on corporate and mortgage exposures from a credit risk perspective under different climate scenarios."
   - p. 208: "This pool of high-risk clients is subsequently managed via the climate risk-appetite setting."
- **Recommendation:** Keep `strong`. Add to notes: "ESG Risk Committee described on p. 102."

### 3. ING Group - Diversity & inclusion (`diversity_inclusion` = `full`, cited p. 137)

- **AI flag:** partly supports; AI category `partial`; AI quote found on the page.
- **Finding:** The AI only saw p. 137 (targets and 35% women in senior positions). The pay-gap figures are on the next page, p. 138, as the notes say: unadjusted 27%, adjusted 3%. The quote now includes the p. 138 sentence.
- **Verified quotes:**
   - p. 137: "Targets are set on an annual basis, reviewed and approved by the management boards and Supervisory Board."
   - p. 137: "In 2025, the number of women in senior positions (GJA 22+) was 35 percent, up from 32 percent in 2024."
   - p. 138: "For 2025, using annual fixed remuneration and target bonus, the unadjusted gender pay gap of ING globally was 27 percent."
- **Recommendation:** Keep `full`.

### 4. ING Group - Labour rights (`labor_rights` = `medium`, cited p. 139)

- **AI flag:** partly supports; AI category `weak`; AI quote found on the page.
- **Finding:** The AI suggested `weak` because p. 139 has no social-dialogue structures. They are on p. 90 (works councils and the European Works Council), and p. 358 states that collective bargaining coverage is not reported ("not applicable" in the DMA). That is exactly the `medium` definition: policy and social dialogue described, key labour metrics not reported.
- **Verified quotes:**
   - p. 139: "Based on our assessment, no severe human rights incidents connected to our own workforce were identified in the reporting period (2024: nil)."
   - p. 90: "ING also has a cross-border European Works Council (EWC), which is consulted when decisions are made that affect employees in multiple countries."
   - p. 358: "S1-8 Collective bargaining coverage and social dialogue Based on our DMA outcome, this requirement is not applicable"
- **Recommendation:** Keep `medium`.

### 5. ING Group - Customer protection (`customer_protection` = `building`, cited p. 141)

- **AI flag:** partly supports; AI category `building`; AI quote found on the page.
- **Finding:** p. 141 confirms the Customer Centricity Policy. The revolving-credit compensation is on p. 311, which says the process "is still ongoing and may take until Q2 2026", matching the summary.
- **Verified quotes:**
   - p. 141: "After rolling out the first version of the CCP in 2024, we updated the policy this year to bring elements such as discrimination and access to banking into the Compliance Risk Framework."
   - p. 311: "The compensation process is still ongoing and may take until Q2 2026."
- **Recommendation:** Keep `building`.

### 6. ING Group - Controversy (`controversy` = `moderate`, cited p. 311)

- **AI flag:** partly supports; AI category `moderate`; AI quote found on the page.
- **Finding:** p. 311 confirms the Milieudefensie lawsuit. The Luxembourg AML case is on p. 309: the referral to trial was decided in November 2024, and in December 2025 the Court of Appeal upheld it so the case can be heard. The summary's "cleared ... for trial in December 2025" is correct.
- **Verified quotes:**
   - p. 311: "In March 2025, Milieudefensie started legal proceedings at the Court in Amsterdam against ING by serving the writ of summons."
   - p. 309: "In December 2025, the Court of Appeal upheld the first decision without making any substantive changes, as a result of which the case can now be heard before the Tribunal Correctionnel."
- **Recommendation:** Keep `moderate`.

### 7. ABN AMRO - Emissions disclosure (`emission_disclosure` = `scope1_2_3`, cited p. 287)

- **AI flag:** partly supports; AI category `scope1_2_3`; AI quote not found on the page.
- **Finding:** The AI's quote failed the check because it mixed numbers from different table columns. The own-operations table on p. 287 reports Scope 1, Scope 2 (market- and location-based) and Scope 3 lines, which meets `scope1_2_3` on its own. Financed emissions are on p. 243.
- **Verified quotes:**
   - p. 287: "Total scope 1 emissions 2,025 1,084"
   - p. 287: "Total scope 2 location-based emissions 8,502 7,224"
   - p. 287: "Total scope 3 emissions 20,731 17,419"
- **Recommendation:** Keep `scope1_2_3`.

### 8. ABN AMRO - Climate risk management (`risk_management` = `strong`, cited p. 217)

- **AI flag:** partly supports; AI category `strong`; AI quote found on the page.
- **Finding:** The AI could not find the heatmaps on p. 217. They are on p. 214 (Environmental and Social Risk heatmaps feeding stress testing and risk appetite); p. 210 maps ESG risk drivers to the financial and non-financial risk types; p. 217 has key risk indicators with limits monitored quarterly.
- **Verified quotes:**
   - p. 217: "The ESG risk appetite is defined through key risk indicators (KRIs), which address ESG factors and risks."
   - p. 217: "To ensure ESG risks remain within the approved risk appetite, we set limits and checkpoints and monitor them quarterly at the bank-wide, entity and local levels."
   - p. 210: "ESG risk takes effect in the form of ESG risk drivers and their subsequent transmission channels, affecting the traditional financial and non-financial risk types."
   - p. 214: "These heatmaps inform, for example, the materiality assessment (see the Strategy and business model section for more on impact and financial materiality assessment), the internal stress testing and the risk appetite"
- **Recommendation:** Keep `strong`. ABN AMRO is the only bank of the three that discloses quantified KRIs and limits (see decision D3).

### 9. ABN AMRO - Diversity & inclusion (`diversity_inclusion` = `full`, cited p. 257)

- **AI flag:** supports; AI category `partial`; AI quote found on the page.
- **Finding:** The AI suggested `partial` because p. 257 has no pay-gap figure. The gender pay gap (18%, 2024: 16%) is in the table on p. 258, as the notes say.
- **Verified quotes:**
   - p. 257: "Women currently represent 34% of the Extended Leadership Team against a 48% ambition, with senior and middle management representation also below the 35% target."
   - p. 258: "Gender pay gap 18% 16% Employees with occupational disability"
- **Recommendation:** Keep `full`.

### 10. ABN AMRO - Labour rights (`labor_rights` = `strong`, cited p. 259)

- **AI flag:** partly supports; AI category `medium`; AI quote found on the page.
- **Finding:** The AI suggested `medium` because p. 259 has no human-rights statement. p. 259 gives collective bargaining coverage (93.17%) and p. 261 states that no severe human-rights violations were registered in 2025. Together they meet `strong`.
- **Verified quotes:**
   - p. 259: "The outcome of this metric is 93.17%. This percentage reflects that the Netherlands, Brazil, France, Germany and Belgium each have a CLA in place"
   - p. 261: "In 2025, ABN AMRO did not register any severe human rights violations, including non-compliance with the UN Guiding Principles on Business and Human Rights"
- **Recommendation:** Keep `strong`.

### 11. ABN AMRO - Customer protection (`customer_protection` = `building`, cited p. 365)

- **AI flag:** partly supports; AI category `building`; AI quote found on the page.
- **Finding:** p. 365 confirms the compensation scheme was completed in 2025. The product approval, duty-of-care and complaints policies the summary mentions are on pp. 264-265 (checked).
- **Verified quotes:**
   - p. 365: "The execution of the compensation scheme has been completed in 2025 and the handling of any other matters relating to consumer credits with a variable interest rate has been handed over"
- **Recommendation:** Keep `building`.

### 12. Rabobank - Climate transition plan (`climate_plan` = `science_based`, cited p. 89)

- **AI flag:** partly supports; AI category `science_based`; AI quote found on the page.
- **Finding:** The AI could not find the named pathways on p. 89. They are in the target table on p. 105: SBTi FLAG, CRREM 2.0, IEA NZE, the Dutch Climate Agreement (DCA) and an own methodology for two leasing targets. No external validation is mentioned.
- **Verified quotes:**
   - p. 89: "To achieve our 2050 goal, we set GHG emissions reduction targets for 19 prioritized sector x region combinations in our portfolio."
   - p. 89: "These targets cover a significant majority of the financed emissions of our portfolio (61%)."
   - p. 105: "SBTi FLAG Rural Australia"
   - p. 105: "IEA NZE Energy/Power Retail Netherlands"
   - p. 105: "DCA: Dutch Climate Agreement"
- **Recommendation:** Keep `science_based`.

### 13. Rabobank - Financed emissions (`financed_emissions` = `pcaf_full`, cited p. 97)

- **AI flag:** partly supports; AI category `pcaf_full`; AI quote found on the page.
- **Finding:** The AI noted that p. 97 does not name PCAF. p. 99 does: "In Rabobank we use the PCAF standard for accounting and disclosing financed emissions" (also p. 88).
- **Verified quotes:**
   - p. 97: "This year we are able to report financed emissions for 98% (FY 2023: 99%) of the relevant (73% of our total assets (FY 2023: 73%)) on-balance sheet assets."
   - p. 97: "we observed a 10% decrease in our financed emissions (Scopes 1 and 2) on a comparable basis, from 46.9 Mt CO₂e to 42.0 Mt CO₂e."
   - p. 99: "In Rabobank we use the PCAF standard for accounting and disclosing financed emissions."
- **Recommendation:** Keep `pcaf_full`.

### 14. Rabobank - Climate risk management (`risk_management` = `strong`, cited p. 90)

- **AI flag:** partly supports; AI category `full`; AI quote found on the page.
- **Finding:** p. 90 confirms assessment of ESG drivers per risk type and NGFS-based stress testing feeding ICAAP. p. 95 lists the Risk Appetite Statement, "sector-specific limits" and changing risk appetite for non-compliant customers as portfolio levers, but only as examples ("e.g. ... etcetera"), with no quantified limits or KRIs. The written definition of `strong` (integrated, quantified with stress testing, limited through risk appetite) is met in words; the disclosure is thinner than ABN AMRO's.
- **Verified quotes:**
   - p. 90: "We assess the impact of these ESG drivers on each risk type within our Risk Taxonomy."
   - p. 90: "The outcomes are integrated in key internal processes such as ICAAP and transition planning."
   - p. 95: "Risk Appetite Statement, e.g., changing our risk appetite for customers who are not compliant with our sustainability policy, sector-specific limits, etcetera."
- **Recommendation:** Keep `strong` (the definition as approved is met, and ING's disclosure is similar). If you want to reward quantified limits, change the definition for all banks instead (D3).

### 15. Rabobank - Diversity & inclusion (`diversity_inclusion` = `full`, cited p. 130)

- **AI flag:** supports; AI category `full`; AI quote not found on the page.
- **Finding:** The AI's quote failed the check because it reordered table cells. p. 130 gives the adjusted (1.25%) and unadjusted (23.30%) gender pay gaps; p. 129 says targets exist for gender diversity in top management.
- **Verified quotes:**
   - p. 130: "Adjusted gender pay gap 1.25% 2024: 1.39%*/1.30%"
   - p. 130: "Unadjusted gender pay gap 23.30% 2024: 24.26%*/20.00%"
   - p. 129: "These targets concern gender diversity in top management and the engagement scan score."
- **Recommendation:** Keep `full`.

### 16. Rabobank - AML maturity (`aml_maturity` = `mature`, cited p. 62)

- **AI flag:** supports; AI category `mature`; AI quote not found on the page.
- **Finding:** The AI's quote failed the check because the PDF has the Dutch name of the AML law in brackets inside the sentence. The sentence is on p. 62: remediation under the DNB instruction completed, controls now being embedded. The prosecution is in the controversy row.
- **Verified quotes:**
   - p. 62: "Following the completion of the remediation of compliance deficiencies related to the Dutch Anti-Money Laundering and Anti-Terrorist Financing Act"
   - p. 62: "Rabobank has continued to embed and maintain robust, operationally effective controls within its day-to-day business processes."
- **Recommendation:** Keep `mature`.

### 17. Rabobank - Board independence (`board_independence` = `>=50`, cited p. 172)

- **AI flag:** supports; AI category `not_disclosed`; AI quote found on the page.
- **Finding:** p. 172 states only that the Supervisory Board "continued to meet best practices provisions 2.1.7 thru 2.1.9" on independence. No count of independent members is given there or on pp. 168-173. The category rests on the reading recorded in our notes that provision 2.1.7 allows fewer than half of the members to be non-independent. The AI, which applies the definition literally (a share of members), chose `not_disclosed`.
- **Verified quotes:**
   - p. 172: "The Supervisory Board, in its current composition, continued to meet best practices provisions 2.1.7 thru 2.1.9 of the Dutch Corporate Governance Code, concerning requirements of independency."
- **Recommendation:** Keep `>=50`, with the inference stated in the notes (already there). `not_disclosed` would score a bank that confirms code compliance the same as one that says nothing.

## Decisions for the analysts

Effects on the scores are computed in [`docs/scoring_options.md`](scoring_options.md). None of the
options changes a compliance label or the ranking.

| # | Question | Recommended | Alternative and effect | Decision |
|---|---|---|---|---|
| D1 | Rabobank climate risk management | keep `strong` | `full`: Rabobank 72.3 -> 71.5 | keep `strong` (decided 18 Oct 2026) |
| D2 | Rabobank board independence | keep `>=50` | `not_disclosed`: Rabobank 72.3 -> 69.2 | keep `>=50` (decided 18 Oct 2026) |
| D3 | Should `strong` risk management require disclosed quantified limits or KRIs? | no change now; consider it from the next reporting year | yes: ING 74.7 -> 74.0 and Rabobank 72.3 -> 71.5 (only ABN AMRO discloses quantified KRIs) | no change now (decided 18 Oct 2026) |
| D4 | Score the three numeric indicators continuously instead of in bands? | no: the effect is at most ±0.2 points and it adds a new convention (band midpoints) | yes: ING 74.9, ABN AMRO 68.8, Rabobank 72.1 | not adopted (decided 18 Oct 2026) |
| D5 | Rabobank labour rights summary says Rabobank "is not aware of severe human-rights incidents"; p. 128 says it has "no internal registration of severe human rights issues and incidents ... given that such complaints are not received" | reword to: "it has no registration of severe human-rights incidents in its Dutch workforce, as no such complaints were received" | keep the current wording | reworded (applied 18 Oct 2026) |
| D6 | ING climate risk management notes | add "ESG Risk Committee described on p. 102." | leave the notes as they are | note added (applied 18 Oct 2026) |

Changing the definition of a category after seeing the results (D3) would look like tuning, which is
why the recommendation is to apply any such change from the next reporting year.

## Other checks made during the re-check

- Number-based categories: the Green Asset Ratio, board independence and ESG-linked pay figures stated in
  the quotes give exactly the current categories for all banks, except Rabobank's board independence, where
  no number is stated (D2). See `docs/scoring_options.md`, section 1.
- Every one of the 45 rows now has at least one verbatim excerpt from its cited page (88 excerpts in total,
  all found on their pages).
