# Revision Spec: ESG-Insight-Platform

Put this file at `docs/ESG_FIX_SPEC.md` in the repo. It is the single source of truth for this revision. Read it fully before doing anything.

---

## 0. Context and how we work

- This repo is a **Columbia industry-sponsored course project with Accenture (Sep–Nov 2025)** that benchmarks ESG performance for ING, ABN AMRO, and Rabobank. I built it early, when I was still learning AI coding tools. I am now revising it because it is linked from my resume and recruiters may read the code.
- I am an Operations Research M.S. student, **not a software engineer**. You write the code; I make the judgments, especially the ESG evidence judgments.
- **Language:** talk to me in Simplified Chinese (简体中文) in chat. Write all code, comments, and docs in English.
- **Workflow:** create a branch `revision-2026`. Work phase by phase (Section 7). At the end of each phase, STOP, summarize in Chinese what changed and why, and wait for my approval. Merge to `main` only after the final phase, and only when I say so. **Never rewrite or force-push git history.**
- **Never fabricate** evidence, quotes, page numbers, sources, or results. If something cannot be found, say so and mark it explicitly.

---

## 1. Problems found in the current code (must all be fixed)

### P1 (critical): fallback scoring is random, not evidence-based
`server.py → Server._fallback_categories()` picks every rubric category (`climate_plan`, `board_independence`, and so on) with `random.Random(seed)`, seeded by a hash of the bank name. When the local LLM is unavailable, and in comparison mode, the ESG scores therefore come from **random choices, not from bank disclosures**. This contradicts the README's "explainable and reproducible ESG assessments" and my resume's "auditable rationale for every score."

### P2 (critical): the "Monte Carlo" confidence band is fake
`server.py → Server._mc_band()` sets the band to roughly ±8 points around the final score, plus random noise. It is not an uncertainty estimate and must be removed.

### P3: LLM outputs are deliberately non-reproducible
`local_llm.py → _fresh_rng()` and `_augment_prompt()` inject entropy based on `time.time()` into the prompts, so every run produces different output.

### P4: the project does not run
The code imports from `tools.*` and `agents.*` packages (for example, `from tools.score_engine import ScoreEngine` and `from agents.esg_agent import ESGAgent`), but every file sits flat at the repo root, so the app fails with `ModuleNotFoundError`.

### P5: dependencies are wrong
`feedparser` and `matplotlib` are imported but missing from `requirements.txt`. `tavily-python` and `pycryptodome` are listed but appear unused (verify with grep before removing). `PyPDF2` is deprecated; consider `pypdf` and test after any change.

### P6: README problems
There are two identical READMEs (`README.md` and `readme.md`). A code block is never closed, so the rest of the page renders as code. `ollama pull` is missing the model name. The installation steps are duplicated. There are no screenshots, no results, no project context (course, sponsor, team, my role), and no limitations section.

---

## 2. Target design: evidence-based, auditable scoring

### 2.1 Evidence table (the new single source of truth for scores)
Create `data/evidence/esg_evidence.csv` with **one row per bank × rubric indicator** (25 indicators × 3 banks = 75 rows). Columns:

| Column | Meaning |
|---|---|
| `bank` | ING Group / ABN AMRO / Rabobank |
| `indicator` | Rubric key exactly as used in `score_engine.py` (for example, `climate_plan`) |
| `category` | Must be one of the allowed values for that indicator, taken from `score_engine.py`, or `not_disclosed` |
| `evidence_summary` | 1–2 sentences in my own words: what the disclosure says |
| `source_document` | For example, "ING Annual Report 2024" |
| `page` | Page number in the PDF |
| `url` | Official URL of the document |
| `status` | `draft` (proposed by you) / `confirmed` (approved by me) |
| `notes` | Optional |

**Rules**
- First, extract the full list of indicators and their allowed category values from `score_engine.py` and show it to me as a table.
- **Drafting:** use the official annual / sustainability / CSRD reports (the latest available year) to propose a category and an evidence summary for each row. Cite the exact page. If you cannot find the evidence, set `category = not_disclosed` and explain in `notes`. **Never guess a page number.**
- All rows start as `draft`. I review them and change them to `confirmed`. Show me the drafts one bank at a time.
- `not_disclosed` maps to the lowest score for that indicator, and the UI flags it.

### 2.2 Scoring flow after the revision
1. Scores are computed **only** from `esg_evidence.csv` through `ScoreEngine`. The flow is deterministic and identical with or without the LLM.
2. The LLM becomes **optional and advisory**. It can summarize PDFs and news and suggest categories, but its suggestions appear in the UI labeled "AI suggestion, not used in score" and never change a score automatically.
3. Delete `_fallback_categories()` and every use of `random` in the scoring path.
4. For every sub-score, the UI shows a breakdown: indicator → category → evidence summary → source and page link.

### 2.3 Replace the fake band with a real sensitivity analysis
Delete `_mc_band()`. Add `tools/sensitivity.py`:
- **Weight sensitivity:** vary the E/S/G pillar weights over a grid (each pillar ±10 percentage points, renormalized to sum to 1) and report how often the bank ranking changes.
- **Judgment sensitivity:** move each indicator one category up and down, one at a time, and report which indicators could change the ranking.
- **UI output:** a short "Robustness" panel, for example "The ranking is unchanged in X% of weight scenarios; the most decisive indicators are …".

### 2.4 LLM reproducibility
Remove the entropy injection from `local_llm.py`. Use temperature 0 and a fixed `seed` in the Ollama request options. Cache LLM outputs by a hash of the input.

---

## 3. Code structure and dependencies
- Create `tools/` and `agents/` packages with `__init__.py`, and move the files to match the imports (use `git mv` to keep history). Verify every import, including `from agents.news_agent import NewsSummariser`.
- Fix `requirements.txt`: add the missing packages, remove the unused ones (after confirming with grep), and pin versions that you test.
- Add `.env.example` (no real values) and confirm that `.env` is gitignored.
- Remove any dead code that is no longer called after the revision.

---

## 4. Tests (`tests/`, run with `pytest`)
- `ScoreEngine`: category → score mapping, weights sum to 1, scores clamped to the range 0–100, controversy adjustment.
- Evidence table validation: every bank × indicator row exists; every category is allowed; every non-`not_disclosed` row has `source_document`, `page`, and `url`.
- Determinism: running the comparison twice with the LLM disabled gives identical scores.
- Smoke test: the app's backend runs end to end with the LLM disabled.

---

## 5. README rewrite (one file: `README.md`; delete `readme.md`)

Structure:
1. **Title and one-sentence pitch**
2. **Context:** a Columbia industry-sponsored course project with Accenture, Sep–Nov 2025. Team project. **My role:** `[TO BE FILLED BY ME]`. Revised in Oct 2026 to make the scoring fully evidence-based (link to CHANGELOG).
3. **Results:** a table of E/S/G and final scores for the 3 banks, the radar chart, and the robustness result. All values come from an actual run.
4. **Methodology:** the rubric, pillar weights (35/30/35), the controversy adjustment, the compliance label, the evidence table, and the sensitivity analysis.
5. **Screenshots** (2–3)
6. **How to run:** correct code blocks; `ollama pull llama3` is optional.
7. **Limitations:** evidence reflects one reporting year; categories involve analyst judgment; this is not investment advice.
8. **Project structure**

Also add `CHANGELOG.md`: "Nov 2025: original course version. Oct 2026: replaced placeholder fallback scoring with evidence-based scoring; removed the simulated confidence band; added sensitivity analysis; fixed package structure and dependencies."

---

## 6. Wording to keep consistent with my resume
My resume says: *"Translated annual, ESG, and CSRD reports into five auditable scoring dimensions — environmental, social, governance, controversy, and compliance."* Make sure the README and the UI describe the model in a way that matches this: E, S, and G pillars, plus a controversy adjustment and a compliance label. If you find a mismatch, tell me rather than changing my resume wording.

---

## 7. Phases and checkpoints

| Phase | Work | Checkpoint |
|---|---|---|
| 1 | Create the branch, fix the package structure and dependencies, make the app run as-is. Show me the indicator/category table. | STOP |
| 2 | Draft the evidence table, one bank at a time, with page citations | STOP after each bank; I confirm the rows |
| 3 | New scoring flow; remove the random fallback, the fake band, and the entropy; add the advisory LLM labeling | STOP |
| 4 | Sensitivity analysis and the UI Robustness panel | STOP |
| 5 | Tests, README, CHANGELOG, screenshots | STOP |
| 6 | Final review; merge to `main` only when I approve | Done |

At each checkpoint, also give me (in Chinese) **3 likely interview questions** about what changed, with short English answers.
