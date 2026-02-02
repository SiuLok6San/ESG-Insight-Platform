from __future__ import annotations

from typing import Dict, Any, List, Optional


# Core metadata table
_BANKS: Dict[str, Dict[str, Any]] = {
    "ING Group": {
        "canonical": "ING Group",
        "aliases": [
            "ing",
            "ing bank",
            "ing groep",
            "ing groep n.v.",
            "ing group n.v.",
            "ing nl",
        ],
        "country": "Netherlands",
        "hq_city": "Amsterdam",
        "website": "https://www.ing.com/",
        "isin": "NL0011821202",
        "ticker_euronext": "INGA.AS",
        "ticker_nyse": "ING",
        "yahoo_symbol": "INGA.AS",
        "employees": 59000,
        "total_assets_eur_bn": 1000.0,
        "rss_keywords": ["ING", "ING Group", "ING Bank"],
        "short_profile": (
            "ING Group is a Dutch multinational banking and financial services "
            "corporation, offering retail and wholesale banking with a strong "
            "focus on digital channels and sustainability."
        ),
    },

    "ABN AMRO": {
        "canonical": "ABN AMRO",
        "aliases": [
            "abn",
            "abn amro bank",
            "abn amro nv",
            "abn amro group",
        ],
        "country": "Netherlands",
        "hq_city": "Amsterdam",
        "website": "https://www.abnamro.com/",
        "isin": "NL0011540547",
        "ticker_euronext": "ABN.AS",
        "ticker_nyse": None,
        "yahoo_symbol": "ABN.AS",
        "employees": 19000,
        "total_assets_eur_bn": 400.0,
        "rss_keywords": ["ABN AMRO", "ABN AMRO Bank"],
        "short_profile": (
            "ABN AMRO is a Dutch bank with a focus on retail, private and "
            "corporate banking in Northwest Europe, with sustainability and "
            "client due diligence as key pillars."
        ),
    },

    "Rabobank": {
        "canonical": "Rabobank",
        "aliases": [
            "rabo",
            "rabo bank",
            "cooperatieve rabobank",
            "coöperatieve rabobank",
            "rabobank group",
        ],
        "country": "Netherlands",
        "hq_city": "Utrecht",
        "website": "https://www.rabobank.com/",
        "isin": None,
        "ticker_euronext": None,
        "ticker_nyse": None,
        "yahoo_symbol": None,
        "employees": 43000,
        "total_assets_eur_bn": 600.0,
        "rss_keywords": ["Rabobank"],
        "short_profile": (
            "Rabobank is a Dutch cooperative bank with an international focus "
            "on food and agriculture financing, and strong roots in the "
            "domestic retail and SME market."
        ),
    },

    "De Volksbank": {
        "canonical": "De Volksbank",
        "aliases": [
            "volksbank",
            "sns bank",
            "de volksbank nv",
        ],
        "country": "Netherlands",
        "hq_city": "Utrecht",
        "website": "https://www.devolksbank.nl/",
        "isin": None,
        "ticker_euronext": None,
        "ticker_nyse": None,
        "yahoo_symbol": None,
        "employees": 3500,
        "total_assets_eur_bn": 70.0,
        "rss_keywords": ["De Volksbank", "SNS Bank"],
        "short_profile": (
            "De Volksbank is a Dutch state-owned retail bank, operating brands "
            "such as SNS, ASN Bank, RegioBank and BLG Wonen, with a strong "
            "focus on social impact and sustainable banking."
        ),
    },

    "Triodos Bank": {
        "canonical": "Triodos Bank",
        "aliases": [
            "triodos",
            "triodos bank nv",
        ],
        "country": "Netherlands",
        "hq_city": "Zeist",
        "website": "https://www.triodos.com/",
        "isin": "NL0000400677",
        "ticker_euronext": None,
        "ticker_nyse": None,
        "yahoo_symbol": None,
        "employees": 1500,
        "total_assets_eur_bn": 20.0,
        "rss_keywords": ["Triodos Bank", "Triodos"],
        "short_profile": (
            "Triodos Bank is a Dutch ethical bank that only finances companies, "
            "institutions and projects that add social, environmental or "
            "cultural value, positioning itself as a pioneer in sustainable finance."
        ),
    },
}


# ======================================================================
# Public helper functions
# ======================================================================

def list_dutch_banks() -> List[str]:
    """
    Return the list of canonical Dutch bank names used everywhere else.

    Example:
        >>> list_dutch_banks()
        ["ING Group", "ABN AMRO", "Rabobank", "De Volksbank", "Triodos Bank"]
    """
    # 保证稳定排序，方便 UI 显示
    return sorted(_BANKS.keys())


def _normalise(s: str) -> str:
    """Simple normalisation for matching user input."""
    return "".join(s.lower().replace(".", "").replace(",", "").split())


def resolve_bank(name: str) -> Optional[str]:
    """
    Map a free-form user input => canonical bank name.

    Examples:
        "ing" -> "ING Group"
        "ing bank" -> "ING Group"
        "abn amro bank" -> "ABN AMRO"
        "triodos" -> "Triodos Bank"

    Returns
    -------
    canonical_name : str or None
    """
    if not isinstance(name, str):
        return None

    raw = name.strip()
    if not raw:
        return None

    norm = _normalise(raw)

    # 1) Exact match on canonical names
    for canonical in _BANKS.keys():
        if norm == _normalise(canonical):
            return canonical

    # 2) Match on aliases
    for canonical, meta in _BANKS.items():
        for alias in meta.get("aliases", []):
            if norm == _normalise(alias):
                return canonical

    # 3) Fallback: contains check（例如 "ING Groep N.V." 包含 "ing groep"）
    for canonical, meta in _BANKS.items():
        if norm in _normalise(canonical):
            return canonical
        for alias in meta.get("aliases", []):
            if norm in _normalise(alias) or _normalise(alias) in norm:
                return canonical

    return None


def get_bank_metadata(name: str) -> Optional[Dict[str, Any]]:
    """
    Return the full metadata dict for a bank.

    `name` can be:
        - canonical name ("ING Group")
        - any known alias ("ing", "ing bank", "ING Groep N.V.")

    Returns
    -------
    metadata : dict or None

    Example:
        >>> meta = get_bank_metadata("ing")
        >>> meta["isin"]
        'NL0011821202'
    """
    canonical = resolve_bank(name) if name else None
    if not canonical:
        return None
    return _BANKS.get(canonical, {}).copy()