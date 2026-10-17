from typing import Any, Dict, List

import altair as alt
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from server import Server
from tools.evidence import REPORTING_YEAR
from tools.radar_chart import create_esg_radar_chart
from tools.score_engine import CONTROVERSY_DEDUCTION, PILLAR_NAMES

st.set_page_config(page_title="Dutch Bank ESG Benchmark", page_icon="📊", layout="wide")

# Categorical slots 1-3 of the validated reference palette (E, S, G).
PILLAR_COLORS = {"E": "#2a78d6", "S": "#eb6834", "G": "#1baf7a"}
FINAL_COLOR = "#2a78d6"


@st.cache_resource
def get_server() -> Server:
    return Server()


server = get_server()
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
    + ("available. Advisory only; it never changes a score." if server.use_llm else "off (no local LLM running). Scores are unaffected.")
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


def render_breakdown(result: Dict[str, Any]) -> None:
    """Indicator -> category -> evidence -> source page, per pillar."""
    breakdown: List[Dict[str, Any]] = result["breakdown"]
    documents = sorted({item["source_document"] for item in breakdown if item["source_document"]})
    st.caption(f"Source: {', '.join(documents)}. Page links open the PDF at the cited page.")
    for pillar, name in PILLAR_NAMES.items():
        lines = [
            f"**{name} - {result['scores']['pillars'][pillar]:.1f}**",
            "",
            "| Indicator | Category | Score | Weight | Evidence | Source |",
            "|---|---|---|---|---|---|",
        ]
        for item in (i for i in breakdown if i["pillar"] == pillar):
            category = "⚠️ not disclosed" if item["not_disclosed"] else f"`{item['category']}`"
            source = f"[p. {item['page']}]({item['page_url']})" if item["page"] else "-"
            if item["status"] != "confirmed":
                source += " (draft)"
            evidence = item["evidence_summary"].replace("|", "/")
            lines.append(
                f"| {item['label']} | {category} | {item['score']} | {item['weight']:.0%} | {evidence} | {source} |"
            )
        st.markdown("\n".join(lines))

    c = result["controversy_evidence"]
    st.markdown(
        f"**Controversy - {c['category']} (−{CONTROVERSY_DEDUCTION.get(c['category'], 5):g} points)**: "
        f"{c['evidence_summary']} [{c['source_document']}, p. {c['page']}]({c['page_url']})"
    )
    if result["draft_indicators"]:
        st.warning(f"Unreviewed (draft) evidence rows: {', '.join(result['draft_indicators'])}")
    if any(item["not_disclosed"] for item in result["breakdown"]):
        st.warning("⚠️ Some indicators are not disclosed in the report; they receive the lowest score.")
    with st.expander("Analyst notes per indicator"):
        for item in breakdown:
            if item["notes"]:
                st.markdown(f"- **{item['label']}**: {item['notes']}")


def render_assistant(assistant: Dict[str, Any]) -> None:
    st.markdown("### 🤖 AI assistant (advisory only)")
    if not assistant.get("enabled"):
        st.info(
            "The AI assistant is off because no local LLM is running. It is optional and never changes the "
            "scores. To enable it, install Ollama and run `ollama pull llama3`."
        )
        return
    if assistant.get("error"):
        st.warning(f"The AI assistant stopped early: {assistant['error']}")

    if assistant.get("suggestions"):
        st.markdown("**AI suggestion, not used in score**")
        df = pd.DataFrame(
            [
                {
                    "Indicator": s["label"],
                    "Evidence category (used)": s["evidence_category"],
                    "AI suggestion (not used)": s["ai_suggestion"] or "-",
                    "Agrees": "✓" if s["agrees"] else "",
                }
                for s in assistant["suggestions"]
            ]
        )
        st.dataframe(df, hide_index=True)
        if assistant.get("rejected"):
            st.caption(f"AI values outside the rubric were ignored: {assistant['rejected']}")

    for title, key in (
        ("AI narrative report", "report"),
        ("AI analysis", "analysis_text"),
        ("AI summary of the annual report", "pdf_summary"),
        ("AI summary of ESG news", "news_summary"),
    ):
        if assistant.get(key):
            with st.expander(f"{title} (not used in score)"):
                st.markdown(assistant[key])


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
    st.markdown("### Optional: news context and AI assistant")
    st.caption("Fetches news and market data and, if a local LLM is running, AI suggestions. Scores above do not change.")
    question = ""
    uploaded_pdf = None
    if server.use_llm:
        question = st.text_area("Focus question for the AI assistant (optional)", height=100)
        uploaded_pdf = st.file_uploader("Extra PDF for the AI assistant (optional)", type=["pdf"])

    if st.button("Load context", type="primary"):
        pdf_text = ""
        if uploaded_pdf is not None:
            from tools.pdf_fetcher import pdf_bytes_to_text

            pdf_text = pdf_bytes_to_text(uploaded_pdf.getvalue())
        with st.spinner("Fetching news and running the AI assistant..."):
            result = server.analyze_bank(
                bank=bank,
                question=question or None,
                pdf_text=pdf_text or None,
                pdf_filename=uploaded_pdf.name if uploaded_pdf else None,
            )
        render_context(result)
        render_assistant(result["assistant"])
    elif not server.use_llm:
        render_assistant({"enabled": False})
