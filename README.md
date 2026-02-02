# 🇳🇱 Dutch Bank ESG Intelligence System

An AI-assisted（Local LLM） ESG (Environmental, Social, Governance) analytics and benchmarking system
for major Dutch banks, including **ING Group**, **ABN AMRO**, and **Rabobank**.

This project is designed as an **institution-style ESG intelligence prototype**.
It integrates public data sources, official bank disclosures, deterministic scoring logic,
and optional local LLM reasoning to generate **explainable and reproducible ESG assessments**.

A core design goal is **robustness**: the system continues to function even when
local LLM inference or external data sources are unavailable.

---

## ✨ What This System Does

- Performs ESG analysis for a **single bank** or **multiple banks (comparison)**
- Extracts ESG signals from:
  - Official annual / sustainability PDF reports
  - Yahoo Finance business profiles
  - Google News RSS (ESG-related headlines)
- Converts qualitative ESG evidence into **0–100 numeric scores**
- Generates:
  - ESG pillar scores (E / S / G)
  - Detailed rubric sub-scores
  - A final ESG score and compliance label
  - Radar charts and comparison tables
  - A structured ESG intelligence report

---

## 🚀 Key Features

### Dual Analysis Modes

**Single Bank Analysis**
- Optional PDF upload (annual / sustainability reports)
- ESG reasoning assisted by a local LLM (if available)
- Outputs ESG scores, confidence bands, radar charts, and a detailed report

**Bank Comparison Mode**
- Fast comparison across multiple banks
- Uses deterministic rubric scoring and public signals
- Produces ranked ESG tables and comparison charts

---

### Hybrid ESG Scoring Engine (v3.0)

- Accepts either qualitative ESG categories or direct numeric ESG scores
- Converts signals into strict **0–100 E / S / G scores**
- Weighted aggregation:
  - Environmental (35%)
  - Social (30%)
  - Governance (35%)
- Fully deterministic, explainable, and reproducible

---

### Robust Fallback Design

- If the local LLM is unavailable, the system automatically switches to deterministic scoring
- If external data is missing, analysis degrades gracefully without breaking the UI
- Safe for live demos, academic presentations, and offline environments

---

## 🛠️ System Architecture

```text
Streamlit UI (app_v2.py)
        │
        ▼
Backend Orchestrator (server.py)
        │
 ┌──────┴────────────────────┐
 ▼                           ▼
LLM-Assisted Agents           Deterministic Tools
--------------------          -------------------
- ESGAgent                   - ScoreEngine
- NewsAgent                  - YahooFinanceClient
- FinalWriterAgent           - Google News RSS
- NLUAgent                   - Radar Chart Generator
                              - PDF Fetcher & Summarizer

Dutch_Bank_ESG/
├── app_v2.py                 # Streamlit UI (main entry)
├── server.py                 # Backend orchestrator
├── requirements.txt          # Python dependencies
├── .env                      # Optional environment config
│
├── agents/                   # LLM-assisted reasoning layer
│   ├── esg_agent.py
│   ├── news_agent.py
│   ├── final_writer.py
│   └── nlu_agent.py
│
└── tools/      
    ├── score_engine.py
    ├── radar_chart.py
    ├── yahoo_client.py
    ├── free_news.py
    ├── pdf_fetcher.py
    ├── pdf_summarizer.py
    └── dutch_banks.py


📦 Installation & Setup

To run the system locally, ensure you have Python 3.9 or higher installed and that
pip is available. Creating a virtual environment is recommended but not required.

First, create and activate a virtual environment:

python -m venv venv
source venv/bin/activate        # macOS / Linux
# or
venv\Scripts\activate           # Windows

pip install -r requirements.txt

# Install all required Python packages:

pip install -r requirements.txt

This installs Streamlit (UI), PDF parsing libraries, data processing tools,
news and finance clients, and visualization utilities.

The system optionally supports local LLM inference via Ollama for deeper ESG
reasoning and report generation. To enable this feature, install Ollama from
https://ollama.com
 and run a local model, for example:

ollama pull
 ollama run llama3

If no local LLM is running, the system will automatically fall back to
deterministic ESG scoring while keeping all charts and tables functional.

Finally, start the Streamlit dashboard:
streamlit run app_v2.py
