# Changelog

## October 2026: after the revision

- **Continuous integration.** GitHub Actions runs the test suite on every push and pull request (Python 3.12, Linux); the README shows the status badge.
- **Live demo** deployed on Streamlit Community Cloud and linked from the README.
- **AI evidence review.** An offline LLM check of every evidence row against its cited page, with verbatim-quote verification. Results are shown in the app as "not used in score". It uses an OpenAI-compatible client (Ollama Cloud by default; Gemini, Groq or local Ollama by configuration), and adds tests plus a guard that fails if an API key is ever committed. First run (Ollama Cloud, gemma4:31b): 32 of 45 rows fully supported, 13 partly, 0 not supported; same category in 39 of 45; 42 of 45 quotes verified.

## October 2026: evidence-based revision

Replaced placeholder fallback scoring with evidence-based scoring; removed the simulated confidence band; added sensitivity analysis; fixed package structure and dependencies.

### Scoring
- **Placeholder scoring replaced.** When the local LLM was unavailable, which included the usual comparison runs, the course prototype filled the rubric categories with placeholder values generated per bank rather than values taken from disclosures. That is replaced by a reviewed evidence table, `data/evidence/esg_evidence.csv`: 45 rows (3 banks × 15 indicators), each citing a page in the bank's FY2025 annual report.
- **Scores come only from the evidence table.** They are identical with or without the LLM.
- **The LLM is advisory.** Its category suggestions are shown as "AI suggestion, not used in score".
- **The engine fails loudly.** It raises an error for missing indicators or invalid categories instead of silently using a mid-range default, and `not_disclosed` maps to the lowest score.
- **LLM-numbers path removed.** The path that accepted E/S/G numbers directly from the LLM is gone.
- **Controversy adjustment added:** 0 / −2 / −5 points. The compliance label is now assigned from the displayed one-decimal score.

### Uncertainty
- **Placeholder band removed.** The prototype's "Monte-Carlo confidence band" was a fixed range of about ±8 points around the score, not an uncertainty estimate.
- **Real sensitivity analysis added.** Pillar weights are varied by up to ±10 percentage points (121 scenarios), and each category judgment is moved one step up and down. A Robustness panel shows the results.

### Reproducibility
- **Reproducible prompts.** Prompts no longer include a time-based value, so identical inputs give identical requests.
- **Deterministic LLM calls.** They use temperature 0 and a fixed seed, and responses are cached by a hash of the input.
- **`.env` settings now work.** They were previously read before `load_dotenv()` ran, so `.env` values were ignored.

### Structure and dependencies
- **Packages fixed.** Modules moved into the `tools/` and `agents/` packages that the imports expected; the app previously failed with `ModuleNotFoundError`.
- **Dependencies fixed.**
  - Added the missing `feedparser`, `matplotlib` and `yfinance`.
  - Removed the unused `tavily-python` and `plotly`.
  - Replaced the deprecated `PyPDF2` with `pypdf`, and `pycryptodome` with `cryptography`, which pypdf needs for encrypted reports.
  - Pinned the versions tested on Python 3.12.
- **Report links fixed.** The old links for ING returned HTTP 403, and every ABN AMRO link pointed to the subsidiary ABN AMRO Clearing Bank, not the group. Reports now come from the URLs cited in the evidence table.
- **Dead code removed:** `NLUAgent`, the Playwright scraper, and unsourced bank figures that were passed to the LLM as facts.

### Robustness fixes from the final review
- **Stricter evidence validator.** It rejects page 0, and reports a malformed CSV row as a validation error instead of crashing.
- **Consistent "not disclosed" citations.** A `not_disclosed` row reads "not disclosed" in the UI and report instead of producing an empty link or "p. None".
- **News feeds can't hang the app.** Each Google News query has a 10-second timeout, and the queries run in parallel.
- **Bounded cache.** The server cache is capped at 64 entries.
- **LLM status rechecked.** Starting Ollama after the app is picked up without a restart.
- **AI summary reads the cited pages.** It summarises the pages the evidence cites instead of the first ~24k characters of the report.
- **No more bad cached reports.** A non-PDF download (e.g. an HTML block page) is no longer cached as the report.

### Documentation and tests
- **README rewritten.** It was previously duplicated as `README.md` / `readme.md`, which collide on case-insensitive file systems.
- **Pinned README numbers.** It now includes context, results from an actual run, methodology, screenshots and limitations; the results are pinned by `tests/test_published_results.py`.
- **`pytest` suite added:** 71 tests covering the scoring engine, evidence validation, determinism, sensitivity analysis, the LLM client, the network clients (mocked) and an end-to-end smoke test of the backend and both Streamlit pages.

## November 2025: original course version

Columbia University industry-sponsored course project with Accenture (September–November 2025).
