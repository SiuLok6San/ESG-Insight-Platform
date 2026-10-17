from __future__ import annotations

from typing import Any, Dict, List

from tools.score_engine import PILLAR_NAMES


class FinalWriterAgent:
    """
    Produces an optional narrative ESG report with the local LLM.

    The scores and categories passed in come from the evidence table and are
    final; the LLM only writes prose around them and is told not to change them.

    Inputs
    ------
    bank : str
        Bank name.
    scores : dict
        ``BankScore.to_dict()`` output from the score engine.
    breakdown : list of dict
        One entry per indicator with category, score and evidence summary.
    news_summary : str
        ESG news signals summary (may be empty).
    """

    def __init__(self, llm) -> None:
        self.llm = llm

    def _build_prompt(
        self,
        bank: str,
        scores: Dict[str, Any],
        breakdown: List[Dict[str, Any]],
        news_summary: str = "",
    ) -> str:
        pillars = scores.get("pillars", {})
        tables = []
        for pillar, name in PILLAR_NAMES.items():
            rows = [
                f"| {item['label']} | {item['category']} | {item['score']} | {item['evidence_summary']} (p. {item['page']}) |"
                for item in breakdown
                if item["pillar"] == pillar
            ]
            header = ["| Indicator | Category | Score | Evidence |", "|---|---|---|---|"]
            tables.append(f"{name} ({pillars.get(pillar)} / 100):\n" + "\n".join(header + rows))
        evidence_tables = "\n\n".join(tables)
        news_block = news_summary.strip() or "No ESG news summary available."

        return f"""
You are an ESG reporting specialist at a European financial supervisor.

Write a concise, factual ESG report for **{bank}** in markdown, using ONLY
the scores and evidence below. The scores are final and come from a reviewed
evidence table: do not change, re-estimate or contradict any number or
category. Cite page numbers when you refer to evidence.

================== SCORES (from the evidence table) ==============
- Environmental (E): {pillars.get('E')} / 100
- Social (S): {pillars.get('S')} / 100
- Governance (G): {pillars.get('G')} / 100
- Controversy: {scores.get('controversy')} (deduction {scores.get('controversy_deduction')} points)
- Final ESG score: {scores.get('final')} / 100 (compliance label: {scores.get('label')})

================== EVIDENCE BY INDICATOR ==========================
{evidence_tables}

================== ESG NEWS SIGNALS (context only) ================
{news_block}

================== TASK ==========================================
Structure:
1. **Executive summary** (2-3 sentences)
2. **Environmental**, **Social**, **Governance**: strengths and gaps, citing pages
3. **Controversy and compliance**: what drives the controversy category
4. **Supervisory focus points** (3-5 bullets)

Keep it under ~800 words. Avoid marketing language.
"""

    def run(
        self,
        bank: str,
        scores: Dict[str, Any],
        breakdown: List[Dict[str, Any]],
        news_summary: str = "",
    ) -> str:
        prompt = self._build_prompt(bank=bank, scores=scores, breakdown=breakdown, news_summary=news_summary)
        return self.llm.ask(prompt)
