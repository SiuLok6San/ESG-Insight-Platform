# Blind AI review

Model: ollama-cloud/gemma4:31b; run on 2026-10-18 with `python -m scripts.review_evidence --blind`.
Not used in the official score. No category was changed.

The model saw only the indicator, the allowed categories with their written definitions, and the text of
the pages each row quotes. It did not see the analysts' category or evidence summary, and the prompt did
not name the bank (the page text often does).

## Agreement

| Measure | Result |
|---|---|
| Blind AI category = analysts' category | 43 of 45 |
| Same measure in the AI evidence review, which was shown the analysts' category | 39 of 45 |
| Blind AI quote found on the pages | 43 of 45 |

The two agreement figures are not a clean measure of anchoring: the AI evidence review saw only the cited
page, while the blind review saw every page the row quotes (for example both p. 137 and p. 138 for ING's
diversity row), so part of the difference comes from the extra pages.

## Every disagreement

Direction: *higher* means the blind AI chose a better-scoring category than the analysts.

| Bank | Indicator | Analysts | Blind AI | Direction | Quote found? | Blind AI's reasoning and quote |
|---|---|---|---|---|---|---|
| Rabobank | Board independence | `>=50` | `not_disclosed` | lower | yes (p. 172) | The text mentions that the Supervisory Board meets independence requirements of the Dutch Corporate Governance Code, but it does not provide the specific share or percentage of independent members. Quote: "The Supervisory Board, in its current composition, continued to meet best practices provisions 2.1.7 thru 2.1.9 of the Dutch Corporate Governance Code, concerning requirements of independency." |
| Rabobank | Controversy | `moderate` | `severe` | lower | yes (p. 327) | The bank disclosed a new fine of EUR 26.6 million imposed by the European Commission for breaching EU competition law, which meets the definition of a severe controversy. Quote: "the Commission fined Rabobank EUR 26.6 million in connection with certain historic communications between a small number of individuals at Deutsche Bank and Rabobank" |

Disagreements are prompts for the analysts to re-check a row, not corrections. The blind AI sees only the
quoted pages, so it can miss evidence elsewhere in the report, and it applies the definitions literally.
