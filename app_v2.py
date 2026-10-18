import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import altair as alt
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
BACKEND_PACKAGES = ("server", "tools", "agents")


def backend_fingerprint() -> str:
    """Hash of the backend code and data files."""
    paths = (
        [ROOT / "server.py"]
        + sorted((ROOT / "tools").glob("*.py"))
        + sorted((ROOT / "agents").glob("*.py"))
        + sorted((ROOT / "data" / "evidence").glob("*"))
    )
    digest = hashlib.sha256()
    for path in paths:
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def drop_stale_backend(fingerprint: str) -> None:
    """Forget backend modules that were imported from older files.

    After a redeploy, Streamlit re-runs this script with the new code, but
    modules imported earlier (server, tools.*, agents.*) stay in memory. The
    ``server`` module is tagged with the fingerprint of the files it was
    imported from; if the files have changed since, all backend modules are
    dropped so the imports below load the new versions together.
    """
    server_module = sys.modules.get("server")
    if server_module is None:
        return
    tag = getattr(server_module, "_backend_fingerprint", None)
    # Modules from the release before this check carry LOADED_FINGERPRINT instead of a tag: treat them as stale.
    if tag is None and not hasattr(server_module, "LOADED_FINGERPRINT"):
        server_module._backend_fingerprint = fingerprint  # imported from the current files
    elif tag != fingerprint:
        for module_name in [m for m in list(sys.modules) if m.split(".")[0] in BACKEND_PACKAGES]:
            del sys.modules[module_name]


BACKEND_FINGERPRINT = backend_fingerprint()
drop_stale_backend(BACKEND_FINGERPRINT)

from server import Server  # noqa: E402  (imported after the stale-module check)
from tools.evidence import REPORTING_YEAR  # noqa: E402
from tools.quota import DailyLimitReached  # noqa: E402
from tools.radar_chart import create_esg_radar_chart  # noqa: E402
from tools.score_engine import PILLAR_NAMES  # noqa: E402

sys.modules["server"]._backend_fingerprint = BACKEND_FINGERPRINT

st.set_page_config(page_title="Dutch Bank ESG Benchmark", page_icon="📊", layout="wide")

# Categorical slots 1-3 of the validated reference palette (E, S, G).
PILLAR_COLORS = {"E": "#2a78d6", "S": "#eb6834", "G": "#1baf7a"}
FINAL_COLOR = "#2a78d6"


@st.cache_resource(max_entries=1)
def get_server(fingerprint: str) -> Server:
    # Keyed on the backend fingerprint: changed code or data builds a fresh Server.
    return Server()


def load_secrets_into_env() -> None:
    """Expose LLM settings stored as Streamlit secrets (e.g. on Streamlit Cloud) as environment variables."""
    try:
        secrets = {k: st.secrets[k] for k in st.secrets}
    except Exception:  # no secrets file: nothing to load
        return
    for name in (
        "OLLAMA_API_KEY",
        "LLM_PROVIDER",
        "OLLAMA_CLOUD_MODEL",
        "AI_QUESTIONS_PER_SESSION",
        "AI_QUESTIONS_PER_DAY",
    ):
        value = secrets.get(name)
        if value and not os.environ.get(name):
            os.environ[name] = str(value)


load_secrets_into_env()
server = get_server(BACKEND_FINGERPRINT)
server.refresh_llm_status()
BANKS = server.banks()

st.sidebar.title("⚙️ Configuration")
mode = st.sidebar.radio("Mode", ["Compare banks", "Single bank"])
st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**How scores are made.** Every score comes from a reviewed evidence table built from the banks' "
    f"{REPORTING_YEAR} annual reports: 14 rubric indicators across Environmental, Social and Governance "
    "pillars (35/30/35), a controversy adjustment, and a compliance label. The same inputs always give "
    "the same scores."
)
st.sidebar.markdown(
    "**AI assistant:** "
    + (
        f"available ({server.llm.describe()}). Advisory only; it never changes the official score."
        if server.use_llm
        else "off (no LLM configured). Scores are unaffected."
    )
)


# Rendering helpers
def render_score_cards(scores: Dict[str, Any]) -> None:
    p = scores["pillars"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Environmental (E)", f"{p['E']:.1f}")
    c2.metric("Social (S)", f"{p['S']:.1f}")
    c3.metric("Governance (G)", f"{p['G']:.1f}")
    c4.metric(
        f"Controversy ({scores['controversy']})",
        f"−{scores['controversy_deduction']:.1f}",
        help=f"Points deducted from the weighted E/S/G score ({scores['weighted']:.1f}).",
    )
    c5.metric("Final ESG score", f"{scores['final']:.1f}", help="0.35×E + 0.30×S + 0.35×G − controversy deduction")
    st.markdown(f"**Compliance label:** {scores['label']}  ·  Meet ≥ 75, Almost Meet ≥ 50, otherwise Not Meet")


def render_calculation(scores: Dict[str, Any]) -> None:
    """Show how the final score follows from the pillar scores."""
    cfg = server.engine.cfg
    p = scores["pillars"]
    st.markdown("**How the final score is calculated**")
    st.markdown(
        f"1. Weighted E/S/G: {cfg.w_E:.2f} × {p['E']:.1f} + {cfg.w_S:.2f} × {p['S']:.1f} + "
        f"{cfg.w_G:.2f} × {p['G']:.1f} = **{scores['weighted']:.1f}**\n"
        f"2. Controversy ({scores['controversy']}): −{scores['controversy_deduction']:.1f}\n"
        f"3. Final score: **{scores['final']:.1f}** → label **{scores['label']}**"
    )
    st.caption(
        "Pillar scores are weighted averages of the indicator scores below. Weighted and final scores are "
        "computed from unrounded pillar scores and then rounded to one decimal."
    )


def render_radar(scores: Dict[str, Any], bank: str) -> None:
    p = scores["pillars"]
    fig = create_esg_radar_chart(p["E"], p["S"], p["G"], bank_name=bank)
    st.pyplot(fig, clear_figure=True, width="content")
    plt.close(fig)


AI_VERDICT_LABELS = {
    "supports": "✓ supports",
    "partially_supports": "◐ partly supports",
    "does_not_support": "✗ does not support",
}


def ai_check_text(review: Any) -> str:
    """Short table cell for the offline AI evidence review (not used in score)."""
    if not review:
        return "-"
    text = AI_VERDICT_LABELS.get(review["ai_verdict"], "? invalid answer")
    if not review["category_agrees"] and review["ai_suggested_category"]:
        text += f" · suggests `{review['ai_suggested_category']}`"
    if not review["quote_verified"]:
        text += " · quote not found"
    return text


def render_breakdown(result: Dict[str, Any]) -> None:
    """Indicator -> category -> evidence -> source page, per pillar."""
    breakdown: List[Dict[str, Any]] = result["breakdown"]
    documents = sorted({item["source_document"] for item in breakdown if item["source_document"]})
    st.caption(f"Source: {', '.join(documents)}. Page links open the PDF at the cited page.")
    has_review = any(item["ai_review"] for item in breakdown)
    for pillar, name in PILLAR_NAMES.items():
        lines = [
            f"**{name} - {result['scores']['pillars'][pillar]:.1f}**",
            "",
            "| Indicator | Category | Score | Weight | Evidence | Source |" + (" AI check* |" if has_review else ""),
            "|---|---|---|---|---|---|" + ("---|" if has_review else ""),
        ]
        for item in (i for i in breakdown if i["pillar"] == pillar):
            category = "⚠️ not disclosed" if item["not_disclosed"] else f"`{item['category']}`"
            source = item["page_link"]
            if item["status"] != "confirmed":
                source += " (draft)"
            evidence = item["evidence_summary"].replace("|", "/")
            row = f"| {item['label']} | {category} | {item['score']} | {item['weight']:.0%} | {evidence} | {source} |"
            if has_review:
                row += f" {ai_check_text(item['ai_review'])} |"
            lines.append(row)
        st.markdown("\n".join(lines))
    if has_review:
        st.caption(
            "*AI check: an independent LLM read only the cited page and judged whether it supports the evidence "
            "summary. Not used in score. Details below."
        )

    c = result["controversy_evidence"]
    deduction = result["scores"]["controversy_deduction"]
    detail = c["evidence_summary"] or c["notes"]
    st.markdown(f"**Controversy - {c['category']} (−{deduction:g} points)**: {detail} ({c['source_link']})")
    if has_review:
        st.caption(f"AI check (not used in score): {ai_check_text(c['ai_review'])}")
        with st.expander("AI review details: quotes and explanations (not used in score)"):
            for item in breakdown + [{"label": "Controversy", "ai_review": c["ai_review"]}]:
                review = item["ai_review"]
                if review:
                    found = "found on the page" if review["quote_verified"] else "NOT found on the page"
                    st.markdown(
                        f"- **{item['label']}** ({ai_check_text(review)}): {review['explanation']}  \n"
                        f"  Quote ({found}): \"{review['quote']}\""
                    )
    if result["draft_indicators"]:
        st.warning(f"Unreviewed (draft) evidence rows: {', '.join(result['draft_indicators'])}")
    if any(item["not_disclosed"] for item in result["breakdown"]):
        st.warning("⚠️ Some indicators are not disclosed in the report; they receive the lowest score.")
    with st.expander("Analyst notes per indicator"):
        for item in breakdown:
            if item["notes"]:
                st.markdown(f"- **{item['label']}**: {item['notes']}")


DAILY_LIMIT_MESSAGE = (
    "The demo has used its {limit} AI requests for today (shared by all visitors), to stay within the free "
    "API quota. The limit resets at midnight UTC."
)


def render_assistant(assistant: Dict[str, Any], official: Dict[str, Any]) -> None:
    if not assistant.get("enabled"):
        st.info(
            "The AI assistant is off because no LLM is configured for this app. It is optional and never "
            "changes the scores. To try it on your own computer, set OLLAMA_API_KEY in .env (Ollama Cloud) "
            "or run a local Ollama server."
        )
        return
    if assistant.get("error"):
        st.warning(f"The AI assistant stopped early: {assistant['error']}")

    if assistant.get("analysis_text"):
        st.markdown(f"**AI answer** ({assistant.get('model', 'LLM')}, not used in score)")
        st.markdown(assistant["analysis_text"])

    estimate = assistant.get("ai_estimate")
    if estimate:
        st.markdown("**AI estimate vs official score**")
        ai = estimate["scores"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Official score (evidence)", f"{official['final']:.1f}", help=official["label"])
        c2.metric(
            "AI estimate (not official)",
            f"{ai['final']:.1f}",
            delta=f"{ai['final'] - official['final']:+.1f}",
            delta_color="off",
        )
        c3.metric("AI estimate label", ai["label"])
        if estimate["changed"]:
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Indicator": c["label"], "Evidence category (official)": c["evidence_category"], "AI category": c["ai_category"]}
                        for c in estimate["changed"]
                    ]
                ),
                hide_index=True,
            )
        else:
            st.caption("The AI chose the same category as the evidence for every indicator it classified.")
        if estimate["kept_from_evidence"]:
            st.caption(
                f"{len(estimate['kept_from_evidence'])} indicator(s) the AI did not classify keep the evidence category "
                "in the estimate. The estimate uses the same scoring engine as the official score."
            )

    if assistant.get("suggestions"):
        with st.expander("All AI category suggestions (not used in score)"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Indicator": s["label"],
                            "Evidence category (used)": s["evidence_category"],
                            "AI suggestion (not used)": s["ai_suggestion"] or "-",
                            "Agrees": "✓" if s["agrees"] else "",
                        }
                        for s in assistant["suggestions"]
                    ]
                ),
                hide_index=True,
            )
            if assistant.get("rejected"):
                st.caption(f"AI values outside the rubric were ignored: {assistant['rejected']}")

    for title, key in (
        ("AI summary of the uploaded PDF", "pdf_summary"),
        ("AI summary of ESG news", "news_summary"),
    ):
        if assistant.get(key):
            with st.expander(f"{title} (not used in score)"):
                st.markdown(assistant[key])


def render_report(bank: str, assistant: Dict[str, Any]) -> None:
    """Narrative report, written only when the visitor asks for it (one extra AI request)."""
    if not assistant.get("enabled"):
        return
    report = st.session_state.get(f"ai_report_{bank}")
    if report:
        with st.expander("AI narrative report (not used in score)", expanded=True):
            st.markdown(report)
        return
    news_summary = assistant.get("news_summary", "")
    no_requests_left = server.ai_requests_left_today() == 0 and not server.has_cached_report(bank, news_summary)
    if st.button(
        "Write an AI narrative report",
        key=f"report_button_{bank}",
        disabled=no_requests_left,
        help="Uses one AI request. The report is advisory and not used in score.",
    ):
        try:
            with st.spinner("Writing the report (this can take a minute)..."):
                st.session_state[f"ai_report_{bank}"] = server.write_report(bank, news_summary)
        except DailyLimitReached:
            st.info(DAILY_LIMIT_MESSAGE.format(limit=server.ai_quota.limit))
        except Exception as exc:  # the report is optional; scores are unaffected
            st.warning(f"The AI report could not be written: {exc}")
        else:
            st.rerun()


def render_context(result: Dict[str, Any]) -> None:
    with st.expander("🔎 News and market context (not used in score)"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Yahoo Finance snapshot**")
            st.write(result["yahoo"]["snapshot"] or "No Yahoo data available.")
        with c2:
            st.markdown("**Google News RSS**")
            items = result["news"]["items"]
            if not items:
                st.info("No news items fetched.")
            for it in items[:10]:
                line = f"- [{it['headline']}]({it['url']})" if it["url"] else f"- {it['headline']}"
                if it["source"]:
                    line += f" - *{it['source']}*"
                if it["published"]:
                    line += f" - {it['published']}"
                st.markdown(line)


def render_compare_charts(df: pd.DataFrame) -> None:
    order = df["Bank"].tolist()
    final = (
        alt.Chart(df)
        .mark_bar(size=36, cornerRadiusEnd=4, color=FINAL_COLOR)
        .encode(
            x=alt.X("Bank:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Final:Q", scale=alt.Scale(domain=[0, 100]), title="Final ESG score"),
            tooltip=["Bank", alt.Tooltip("Final:Q", format=".1f"), "Label"],
        )
    )
    threshold = (
        alt.Chart(pd.DataFrame({"y": [75], "text": ["Meet threshold (75)"]}))
        .mark_rule(strokeDash=[4, 4], color="#8a8986")
        .encode(y="y:Q")
    )
    threshold_label = (
        alt.Chart(pd.DataFrame({"y": [75], "text": ["Meet threshold (75)"]}))
        .mark_text(align="left", dx=4, dy=-6, color="#52514e")
        .encode(y="y:Q", x=alt.value(0), text="text:N")
    )

    melted = df.melt(id_vars=["Bank"], value_vars=["E", "S", "G"], var_name="Pillar", value_name="Score")
    pillars = (
        alt.Chart(melted)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("Bank:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("Pillar:N", sort=["E", "S", "G"]),
            y=alt.Y("Score:Q", scale=alt.Scale(domain=[0, 100]), title="Pillar score"),
            color=alt.Color(
                "Pillar:N",
                sort=["E", "S", "G"],
                scale=alt.Scale(domain=list(PILLAR_COLORS), range=list(PILLAR_COLORS.values())),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["Bank", "Pillar", alt.Tooltip("Score:Q", format=".1f")],
        )
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Final ESG score**")
        st.altair_chart((final + threshold + threshold_label).properties(height=280), width="stretch")
    with c2:
        st.markdown("**E / S / G pillar scores**")
        st.altair_chart(pillars.properties(height=280), width="stretch")


def render_robustness(report: Dict[str, Any], ranking: List[str]) -> None:
    n = len(report["weight_results"])
    st.markdown("### 🛡️ Robustness")
    st.caption(
        f"Weight sensitivity: each pillar weight moved by -10 to +10 percentage points in 5-point steps, then "
        f"renormalised ({n} scenarios). Judgment sensitivity: every category moved one step up and down, one at "
        "a time. Rankings use the one-decimal final score; a tie counts as a change."
    )
    for line in report["summary"]:
        st.markdown(f"- {line}")

    rows = [
        {
            "Bank": bank,
            "Lowest": report["final_ranges"][bank][0],
            "Highest": report["final_ranges"][bank][1],
            "Default weights": report["base_finals"][bank],
        }
        for bank in ranking
    ]
    df = pd.DataFrame(rows)
    lo = min(df["Lowest"].min(), 75.0) - 2
    hi = max(df["Highest"].max(), 75.0) + 2
    x_scale = alt.Scale(domain=[lo, hi])
    tooltip = ["Bank", alt.Tooltip("Lowest:Q", format=".1f"), alt.Tooltip("Highest:Q", format=".1f"),
               alt.Tooltip("Default weights:Q", format=".1f")]
    y = alt.Y("Bank:N", sort=ranking, title=None)
    span = alt.Chart(df).mark_rule(strokeWidth=6, strokeCap="round", color=FINAL_COLOR, opacity=0.35).encode(
        y=y,
        x=alt.X("Lowest:Q", scale=x_scale, title="Final ESG score", axis=alt.Axis(format=".0f", tickMinStep=1)),
        x2="Highest:Q",
        tooltip=tooltip,
    )
    point = alt.Chart(df).mark_point(filled=True, size=90, color=FINAL_COLOR, stroke="white", strokeWidth=2).encode(
        y=y, x=alt.X("Default weights:Q", scale=x_scale), tooltip=tooltip
    )
    threshold = alt.Chart(pd.DataFrame({"x": [75]})).mark_rule(strokeDash=[4, 4], color="#8a8986").encode(x="x:Q")
    st.markdown(f"**Final score range across {n} weight scenarios** (dot = default 35/30/35; dashed line = Meet threshold)")
    st.altair_chart((span + point + threshold).properties(height=60 * len(ranking) + 40), width="stretch")
    st.caption(
        "Each bar spans a bank's lowest and highest final score over all weight scenarios. Bars can overlap even "
        "when the ranking never changes, because within one scenario all banks move together."
    )

    moves = [m for m in report["moves"] if m["changes_ranking"] or m["changes_label"]]
    with st.expander(f"Single judgment changes that change the ranking or a label ({len(moves)} of {len(report['moves'])})"):
        if not moves:
            st.write("None.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Bank": m["bank"],
                            "Indicator": m["indicator"],
                            "Change": f"{m['from_category']} → {m['to_category']}",
                            "Final": f"{m['final_before']:.1f} → {m['final_after']:.1f}",
                            "Changes ranking": "yes" if m["changes_ranking"] else "",
                            "Changes label": f"{m['label_before']} → {m['label_after']}" if m["changes_label"] else "",
                        }
                        for m in moves
                    ]
                ),
                hide_index=True,
            )

    with st.expander(f"All {n} weight scenarios"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "w_E": r["weights"]["E"],
                        "w_S": r["weights"]["S"],
                        "w_G": r["weights"]["G"],
                        **{bank: r["finals"][bank] for bank in ranking},
                        "Ranking unchanged": r["ranking_unchanged"],
                    }
                    for r in report["weight_results"]
                ]
            ),
            hide_index=True,
            column_config={w: st.column_config.NumberColumn(format="%.3f") for w in ("w_E", "w_S", "w_G")},
        )


def render_ai_review_summary(summary: Dict[str, Any]) -> None:
    st.markdown("### 🔎 AI evidence review (not used in score)")
    if not summary["rows"]:
        st.caption("The offline AI evidence review has not been run yet.")
        return
    n = summary["rows"]
    v = summary["verdicts"]
    st.markdown(
        f"An independent LLM ({', '.join(summary['models'])}, run on {', '.join(summary['reviewed_on'])}) read each "
        f"cited page and checked the evidence row against it:\n"
        f"- **Supports the evidence summary:** {v['supports']} of {n} rows; partly: {v['partially_supports']}; "
        f"does not support: {v['does_not_support']}\n"
        f"- **Same category as the analyst:** {summary['category_agrees']} of {n}\n"
        f"- **Quote found verbatim on the cited page:** {summary['quote_verified']} of {n}"
    )
    if summary["disagreements"]:
        with st.expander(f"Rows to re-check ({len(summary['disagreements'])})"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Bank": r["bank"],
                            "Indicator": r["indicator"],
                            "Evidence category": r["evidence_category"],
                            "AI check": ai_check_text(r),
                            "AI explanation": r["explanation"],
                        }
                        for r in summary["disagreements"]
                    ]
                ),
                hide_index=True,
            )
    st.caption(
        "The review only sees the single cited page, so 'partly' can be expected where the analyst's notes cite "
        "further pages. Disagreements are prompts to re-check the evidence; they never change a category."
    )


# MODE 1 - Compare banks
if mode == "Compare banks":
    st.title("🏆 Dutch bank ESG benchmark")
    st.caption(f"Evidence: {REPORTING_YEAR} annual reports of ING Group, ABN AMRO and Rabobank.")

    banks = st.multiselect("Banks", BANKS, default=BANKS)
    if not banks:
        st.warning("Select at least one bank.")
        st.stop()

    comparison = server.compare_banks(banks)
    per_bank = comparison["per_bank_results"]
    if comparison["errors"]:
        st.error(f"Some banks could not be scored: {comparison['errors']}")

    rows = []
    for rank, bank in enumerate(comparison["ranking"], start=1):
        sc = per_bank[bank]["scores"]
        rows.append(
            {
                "Rank": rank,
                "Bank": bank,
                "E": sc["pillars"]["E"],
                "S": sc["pillars"]["S"],
                "G": sc["pillars"]["G"],
                "Weighted E/S/G": sc["weighted"],
                "Controversy": f"{sc['controversy']} (−{sc['controversy_deduction']:g})",
                "Final": sc["final"],
                "Label": sc["label"],
            }
        )
    df = pd.DataFrame(rows)

    st.markdown("### 📊 Comparison table")
    st.dataframe(
        df,
        hide_index=True,
        column_config={c: st.column_config.NumberColumn(format="%.1f") for c in ("E", "S", "G", "Weighted E/S/G", "Final")},
    )
    render_compare_charts(df)
    render_robustness(server.sensitivity(comparison["ranking"]), comparison["ranking"])
    render_ai_review_summary(server.ai_review_summary())

    st.markdown("### 📡 Radar charts")
    cols = st.columns(len(comparison["ranking"]))
    for col, bank in zip(cols, comparison["ranking"]):
        with col:
            render_radar(per_bank[bank]["scores"], bank)

    st.markdown("### 🔍 Score breakdown per bank")
    for bank in comparison["ranking"]:
        with st.expander(f"{bank} - {per_bank[bank]['scores']['final']:.1f} ({per_bank[bank]['scores']['label']})"):
            render_score_cards(per_bank[bank]["scores"])
            render_breakdown(per_bank[bank])

# MODE 2 - Single bank
else:
    st.title("🔍 Single bank")
    bank = st.selectbox("Bank", BANKS)

    scored = server.score_bank(bank)
    render_score_cards(scored["scores"])
    c1, c2 = st.columns([1, 2])
    with c1:
        render_radar(scored["scores"], bank)
    with c2:
        render_calculation(scored["scores"])
    st.markdown("### 📑 Score breakdown")
    render_breakdown(scored)

    st.markdown("---")
    st.markdown("### 🤖 Ask the AI assistant")
    if not server.use_llm:
        render_assistant({"enabled": False}, scored["scores"])
    else:
        limit = int(os.getenv("AI_QUESTIONS_PER_SESSION", "5"))
        used = st.session_state.get("ai_questions_used", 0)
        left_today = server.ai_requests_left_today()
        st.caption(
            f"Model: {server.llm.describe()}. The AI answers from the reviewed evidence above (plus recent news), "
            "suggests rubric categories, and shows the score those categories would give. It never changes the "
            f"official score. Questions left in this session: {max(limit - used, 0)} of {limit}. "
            f"AI requests left today for the whole site: {left_today} of {server.ai_quota.limit}."
        )
        question = st.text_area(
            "Your question",
            placeholder=f"e.g. How credible is {bank}'s climate transition plan, and what would change its score?",
            height=100,
            key=f"question_{bank}",
        )
        uploaded_pdf = st.file_uploader("Extra PDF for the AI (optional)", type=["pdf"], key=f"pdf_{bank}")
        if used >= limit:
            st.info(f"This demo allows {limit} AI questions per visit, to stay within the free API quota.")
        elif left_today == 0:
            st.info(DAILY_LIMIT_MESSAGE.format(limit=server.ai_quota.limit))
        if st.button("Ask", type="primary", disabled=used >= limit or left_today == 0):
            pdf_text = ""
            if uploaded_pdf is not None:
                from tools.pdf_fetcher import pdf_bytes_to_text

                pdf_text = pdf_bytes_to_text(uploaded_pdf.getvalue())
            # A question answered from the cache makes no AI request, so it is not counted.
            cached = server.has_cached_analysis(bank, question or None, pdf_text or None)
            try:
                with st.spinner("Asking the AI (this can take about a minute; repeated questions are faster)..."):
                    st.session_state[f"ai_result_{bank}"] = server.analyze_bank(
                        bank=bank,
                        question=question or None,
                        pdf_text=pdf_text or None,
                        pdf_filename=uploaded_pdf.name if uploaded_pdf else None,
                    )
            except DailyLimitReached:
                st.info(DAILY_LIMIT_MESSAGE.format(limit=server.ai_quota.limit))
            else:
                if not cached:
                    st.session_state["ai_questions_used"] = used + 1
                st.rerun()  # redraw so the captions show the new counts
        result = st.session_state.get(f"ai_result_{bank}")
        if result:
            render_assistant(result["assistant"], scored["scores"])
            render_report(bank, result["assistant"])
            render_context(result)
