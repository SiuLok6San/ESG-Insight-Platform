# Category definitions for the evidence table

This file defines how each rubric category in `esg_evidence.csv` is assigned.
The allowed values and their scores come from `tools/score_engine.py`; the
definitions are analyst conventions written down so that the same rule is
applied to every bank. Rows are proposed as `draft` and only become
`confirmed` after review.

## Conventions

- **Reporting year:** FY2025 (annual reports published in early 2026).
- **Page numbers** refer to the PDF page, which for the reports used so far
  equals the printed page number.
- **Enforcement window:** fines, settlements and remediation are considered
  if they occurred in FY2023–FY2025. Older events are mentioned in `notes`
  but do not set the category on their own.
- **Two-tier boards:** Dutch banks have a Supervisory Board (non-executive)
  and an Executive/Management Board. Board independence is measured on the
  Supervisory Board.
- **`not_disclosed`** is used when the report does not contain the evidence.
  It maps to the lowest score of the indicator (see the open question at the
  end of this file).
- **Conservative rule:** when the evidence sits between two categories, the
  lower one is chosen and the alternative is recorded in `notes`.

## Environmental (E) — 35% of the final score

| Indicator | Weight in E | Category = score | Definition |
|---|---|---|---|
| `climate_plan` | 20% | `none`=10, `weak`=40, `science_based`=75, `sbt_aligned`=90 | `sbt_aligned`: targets validated by the Science Based Targets initiative. `science_based`: sector targets derived from a 1.5°C scenario (e.g. IEA NZE) but not externally validated. `weak`: net-zero ambition without sector targets. `none`: no transition plan. |
| `emission_disclosure` | 20% | `none`=5, `scope1`=40, `scope1_2`=70, `scope1_2_3`=90 | Highest GHG scope the bank reports for itself, either for own operations or financed (Scope 3 category 15). |
| `financed_emissions` | 20% | `none`=10, `partial`=60, `pcaf_full`=85 | `pcaf_full`: PCAF-based financed emissions for the main lending asset classes (mortgages, commercial real estate, corporate lending). `partial`: only some sectors or portfolios. `none`: not reported. |
| `taxonomy_alignment` | 15% | `none`=20, `low`=45, `medium`=65, `high`=80, `aligned`=90 | Based on the turnover-based Green Asset Ratio (stock). **Thresholds (approved 2026-10-17):** `low` < 10%, `medium` 10–25%, `high` 25–50%, `aligned` ≥ 50%; `none` = GAR reported as 0%. |
| `risk_management` | 15% | `none`=20, `weak`=45, `partial`=60, `full`=75, `strong`=90 | `strong`: climate and environmental risk integrated across risk types, quantified with scenario analysis or stress testing, and limited through risk appetite. `full`: integrated across risk types without quantified limits. `partial`: integrated in some risk types only. `weak`: qualitative statements. |
| `fossil_policy` | 10% | `none`=20, `weak`=40, `partial`=60, `strong`=80, `exit`=90 | `exit`: no new financing for thermal coal and upstream oil & gas, already in effect. `strong`: dated phase-out commitments for both coal and upstream oil & gas, with measured progress. `partial`: dated phase-out for coal only, or oil & gas restrictions without a date. `weak`: narrow exclusions (e.g. Arctic, oil sands) only. |

## Social (S) — 30% of the final score

| Indicator | Weight in S | Category = score | Definition |
|---|---|---|---|
| `diversity_inclusion` | 25% | `none`=20, `partial`=55, `full`=80 | `full`: quantified diversity targets with reported progress and a disclosed gender pay gap. `partial`: policy and some metrics, but no targets or no pay-gap figure. |
| `labor_rights` | 25% | `none`=20, `weak`=45, `medium`=65, `strong`=85 | `strong`: human-rights and labour policy, social dialogue structures, collective bargaining coverage disclosed, and no severe incidents. `medium`: policy and social dialogue described, but key labour metrics (e.g. collective bargaining coverage) not reported. `weak`: general statements only. |
| `customer_protection` | 25% | `fined`=30, `building`=60, `mature`=80 | `fined`: regulatory fine or sanction for customer treatment in the window. `building`: framework in place but recently introduced, or large customer remediation still running in the reporting year. `mature`: established framework, no material remediation or fines in the window. |
| `aml_maturity` | 25% | `fined`=25, `weak`=40, `building`=60, `mature`=75, `leading`=90 | `fined`: AML fine or settlement in the window. `weak`: regulator-identified deficiencies without remediation. `building`: remediation programme still running or regulatory measures still in place. `mature`: remediation completed, no new enforcement in the window. `leading`: mature plus recognised industry leadership. |

## Governance (G) — 35% of the final score

| Indicator | Weight in G | Category = score | Definition |
|---|---|---|---|
| `board_independence` | 25% | `<33`=45, `33_50`=65, `>=50`=80 | Share of independent Supervisory Board members at year end. |
| `esg_oversight` | 25% | `none`=30, `csr_dept`=60, `board_committee`=80 | `board_committee`: a board-level committee with an explicit ESG or sustainability remit. `csr_dept`: oversight only at management or department level. |
| `exec_comp_esg` | 25% | `none`=40, `<20`=60, `>=20`=80 | Weight of explicitly environmental and social (sustainability) targets in the CEO's variable-remuneration scorecard. |
| `transparency_csrd` | 25% | `non_compliant`=30, `partial`=60, `full`=80 | `full`: sustainability statement prepared under ESRS with an external assurance conclusion. `partial`: ESRS applied only in part, or no external assurance. `non_compliant`: no CSRD/ESRS reporting. |

## Controversy (approved 2026-10-17; not yet in `score_engine.py`)

One row per bank, indicator `controversy`. The score adjustment will be
designed in Phase 3.

| Category | Definition |
|---|---|
| `none` | No ESG-related legal or regulatory proceedings disclosed for the reporting year. |
| `moderate` | ESG-related litigation, criminal proceedings or customer remediation ongoing in the reporting year, without a new fine or settlement. |
| `severe` | A new ESG-related fine, settlement or conviction in the reporting year. |

ESG-related means: climate or environment, financial crime (AML, sanctions,
corruption), customer harm, or human rights. The source is the bank's own
legal-proceedings note in the annual report.

## Open questions for review

Resolved: the GAR thresholds and the controversy categories were approved
on 2026-10-17. The EU does not define GAR bands, so the thresholds remain an
analyst convention.

1. **`not_disclosed` = lowest score** means a bank that does not report on
   customer protection scores the same as a bank that was fined (`fined`=30).
2. **Double counting:** an AML fine would lower both `aml_maturity` and
   `controversy`. Phase 3 should decide whether the controversy adjustment
   excludes events already captured by a `fined` category.
