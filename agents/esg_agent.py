from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from tools.score_engine import CONTROVERSY_KEY, RUBRIC, allowed_categories

try:  # optional, only used to enrich the prompt if available
    from tools.dutch_banks import get_bank_metadata
except Exception:  # pragma: no cover - defensive fallback
    get_bank_metadata = None  # type: ignore


class ESGAgent:
    """
    LLM-based ESG analysis agent (advisory only).

    It reads the context assembled by :class:`Server` and suggests a rubric
    category for each indicator, with a short narrative. The suggestions are
    shown next to the evidence-based categories in the UI but are never used
    to compute a score.

    Parameters
    ----------
    llm :
        Any object exposing ``ask(prompt: str) -> str``, such as
        :class:`tools.local_llm.LocalLLM`.
    """

    def __init__(self, llm) -> None:
        self.llm = llm

    def run(self, bank: str, question: Optional[str], context_blob: str) -> Dict[str, Any]:
        """
        Returns
        -------
        dict
            {
              "analysis_text": str,
              "suggestions": {indicator: category},  # valid categories only
              "rejected": {indicator: value},        # values outside the rubric
            }
        """
        prompt = self._build_prompt(bank=bank, question=question, evidence=context_blob)
        raw = self.llm.ask(prompt)
        analysis_text, parsed = self._split_analysis_and_json(raw)

        suggestions: Dict[str, str] = {}
        rejected: Dict[str, Any] = {}
        for key, value in parsed.items():
            try:
                allowed = allowed_categories(key)
            except KeyError:
                rejected[key] = value
                continue
            if isinstance(value, str) and value in allowed:
                suggestions[key] = value
            else:
                rejected[key] = value

        return {"analysis_text": analysis_text, "suggestions": suggestions, "rejected": rejected}

    # Prompt construction
    def _build_prompt(self, bank: str, question: Optional[str], evidence: str) -> str:
        meta_block = ""
        if get_bank_metadata is not None:
            meta = get_bank_metadata(bank) or {}
            meta_lines = [f"- {k}: {meta[k]}" for k in ("canonical", "country", "website") if meta.get(k)]
            if meta_lines:
                meta_block = "Known static metadata about the bank:\n" + "\n".join(meta_lines)

        focus = question.strip() if question else "overall ESG risk profile and transition credibility"

        rubric_lines = []
        for pillar in ("E", "S", "G"):
            for ind in (i for i in RUBRIC if i.pillar == pillar):
                options = ", ".join(f'"{c}"' for c in ind.categories)
                rubric_lines.append(f'- "{ind.key}" ({pillar}, {ind.label}): one of [{options}]')
        rubric_lines.append(
            f'- "{CONTROVERSY_KEY}": one of ["none", "moderate", "severe"] '
            "(severe = new ESG-related fine, settlement or conviction this year)"
        )
        rubric_block = "\n".join(rubric_lines)
        json_keys = ",\n".join(f'  "{ind.key}": "..."' for ind in RUBRIC) + f',\n  "{CONTROVERSY_KEY}": "..."'

        return f"""
You are a senior EU sustainability supervisor (EBA/ECB/CSRD).

Assess the ESG profile of the bank below using ONLY the evidence that
follows. You MUST NOT invent facts. If data is missing or weak, choose the
more conservative (weaker) option.

Bank: {bank}
User focus: {focus}

{meta_block}

==================== EVIDENCE (bank-specific) ====================
{evidence}
===============================================================

RUBRIC CLASSIFICATION
---------------------
Pick exactly ONE value from the allowed options for each key, or
"not_disclosed" if the evidence does not cover it:

{rubric_block}

Output requirements
-------------------
1. First, answer the user's question directly in plain English (max ~250
   words), based on the evidence above. Cite page numbers (e.g. "p. 111").
   If there is no specific question, give a short assessment of the bank's
   ESG profile. Say so when the evidence does not cover something.
2. Then, on a NEW LINE, output a single JSON object ONLY (no backticks, no
   commentary) with exactly these keys and string values:

{{
{json_keys}
}}
"""

    # Output parsing
    @staticmethod
    def _split_analysis_and_json(raw: str) -> Tuple[str, Dict[str, Any]]:
        """Split the LLM output into narrative text and the last JSON object in it."""
        raw = (raw or "").strip()
        end = raw.rfind("}")
        start = raw.rfind("{", 0, end + 1)
        # Walk back to the outermost "{" whose block parses as JSON.
        while start != -1 and end != -1:
            candidate = raw[start : end + 1]
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                start = raw.rfind("{", 0, start)
                continue
            if isinstance(parsed, dict):
                analysis = (raw[:start] + raw[end + 1 :]).strip() or raw
                return analysis, parsed
            break
        return raw, {}
