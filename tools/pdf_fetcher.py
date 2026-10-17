from __future__ import annotations

import logging
from typing import Dict, List, Optional

from io import BytesIO

import requests

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

logger = logging.getLogger(__name__)


STATIC_PDF_LINKS: Dict[str, Dict[str, List[str]]] = {
    # ING Group / ING Groep N.V.
    "ING Group": {
        "2018": [
            "https://www.annualreports.com/HostedData/AnnualReportArchive/i/NYSE_IDG_2018.pdf",
        ],
        "2019": [
            "https://www.annualreports.com/HostedData/AnnualReportArchive/i/NYSE_IDG_2019.pdf",
        ],
        "2020": [
            "https://www.annualreports.com/HostedData/AnnualReportArchive/i/NYSE_IDG_2020.pdf",
        ],
        "2021": [
            "https://www.annualreports.com/HostedData/AnnualReportArchive/i/NYSE_IDG_2021.pdf",
        ],
        "2022": [
            "https://www.annualreports.com/HostedData/AnnualReportArchive/i/NYSE_IDG_2022.pdf",
        ],
        "2023": [
            "https://www.annualreports.com/HostedData/AnnualReportArchive/i/NYSE_IDG_2023.pdf",
        ],
        "2024": [
            "https://www.annualreports.com/HostedData/AnnualReports/PDF/NYSE_IDG_2024.pdf",
        ],
    },

    #Rabobank
    "Rabobank": {
        "2018": [
            "https://media.rabobank.com/m/77a1773024ad55cb/original/Annual-Report-2018-EN.pdf",
        ],
        "2019": [
            "https://media.rabobank.com/m/62c486618fff551/original/Annual-Report-2019-EN.pdf",
        ],
        "2020": [
            "https://media.rabobank.com/m/afe095da98c3a55/original/Annual-Report-2020-EN.pdf",
        ],
        "2021": [
            "https://media.rabobank.com/m/569cafc747920bd4/original/Annual-Report-2021-EN.pdf",
        ],
        "2022": [
            "https://media.rabobank.com/m/467790ff0c0d80c6/original/Annual-Report-2022-EN.pdf",
        ],
        "2023": [
            "https://media.rabobank.com/m/1ad90f364fe20547/original/Annual-Report-2023.pdf",
        ],
        "2024": [
            "https://media.rabobank.com/m/6139dd32089f1983/original/Annual-Report-2024.pdf",
        ],
        "2025": [
            "https://media.rabobank.com/m/64987e5ced354dcc/original/Interim-Report-2025.pdf",
        ],
    },


    #ABN AMRO
    "ABN AMRO": {
        "2018": [
            "https://assets.ctfassets.net/1u811bvgvthc/1ceG3gQhL4lkdmxqHg7ozk/f6d920f5b7a6219acefee97f3b003a12/AAC_Annual_report_2018.pdf",
        ],
        "2019": [
            "https://assets.ctfassets.net/1u811bvgvthc/kVpoN2ucXqDy4L9zQMKJL/c0c511139568b658dba62411ac5e46f2/AACB_Annual_Report_2019.pdf",
        ],
        "2020": [
            "https://assets.ctfassets.net/1u811bvgvthc/1ksEtQ6JvTAgpWCDa77sdK/9ed2a7ec19f4d81fe5ab9d73a6861a58/AACB_Annual_Report_2020.pdf",
        ],
        "2021": [
            "https://assets.ctfassets.net/1u811bvgvthc/3k31JpmFKJGdhLN0ava2yL/91e2a5f138eaa35295d23542f81c75a7/Annual_Report_2021_-_ABN_AMRO_Clearing.pdf",            
        ],
        "2022": [
            "https://assets.ctfassets.net/1u811bvgvthc/3Az9mUL9SYc6vAcuBAxJ8K/d0fd34d29dddc41eac8aab2809a22577/Annual_Report_2022_-_ABN_AMRO_Clearing.pdf",
        ],
        "2023": [
            "https://assets.ctfassets.net/1u811bvgvthc/15EVHeDNFUV2CjB5KiOiYi/984072b658f21ad496b2f2efff45bf01/AACB_Annual_Report_2023.pdf",
        ],
    },
}


BANK_START_URLS: Dict[str, str] = {
    "ING Group": "https://www.ing.com/Investors/Investors/Financial-performance/Annual-reports.htm",
    "Rabobank": "https://www.rabobank.com/about-us/organization/results-and-reports",
    "ABN AMRO": "https://www.abnamro.com/en/about-abn-amro/information/annual-report-archive",
}


def _download_pdf_text(url: str, timeout: int = 25) -> str:

    if PdfReader is None:
        logger.warning("[PDFFetcher] pypdf not installed; cannot parse PDF.")
        return ""

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[PDFFetcher] Failed to download PDF from {url}: {e}")
        return ""

    try:
        reader = PdfReader(BytesIO(resp.content))
        texts: List[str] = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        text = "\n".join(texts)
        logger.info(f"[PDFFetcher] Extracted {len(text)} chars from {url}")
        return text
    except Exception as e:
        logger.warning(f"[PDFFetcher] Failed to parse PDF from {url}: {e}")
        return ""


def _scrape_pdf_links_with_playwright(start_url: str, max_links: int = 5) -> List[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[PDFFetcher] Playwright not installed; skip browser scraping.")
        return []

    pdf_links: List[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(start_url, timeout=60_000)
            page.wait_for_timeout(5000)

            anchors = page.query_selector_all("a[href$='.pdf']")
            for a in anchors[:max_links]:
                href = a.get_attribute("href")
                if not href:
                    continue
                if href.startswith("/"):
                    from urllib.parse import urljoin
                    href = urljoin(start_url, href)
                pdf_links.append(href)

            browser.close()
    except Exception as e:
        logger.warning(f"[PDFFetcher] Playwright scraping failed for {start_url}: {e}")

    return pdf_links

def fetch_official_pdfs(
    bank: str,
    year: Optional[str] = None,
    use_playwright: bool = False,
) -> List[str]:
    bank_norm = bank.strip()
    texts: List[str] = []

    bank_map = STATIC_PDF_LINKS.get(bank_norm, {})

    urls: List[str] = []
    if year:
        urls = bank_map.get(str(year), [])
    else:
        for _, lst in bank_map.items():
            if lst:
                urls.extend(lst)

    for u in urls:
        t = _download_pdf_text(u)
        if t:
            texts.append(t)

    #Playwright
    if not texts and use_playwright:
        start_url = BANK_START_URLS.get(bank_norm)
        if start_url:
            scraped_urls = _scrape_pdf_links_with_playwright(start_url)
            for u in scraped_urls:
                t = _download_pdf_text(u)
                if t:
                    texts.append(t)

    if not texts:
        logger.info(f"[PDFFetcher] No PDF text found for bank={bank_norm}, year={year}")
    else:
        logger.info(
            f"[PDFFetcher] Got {len(texts)} PDF(s) for bank={bank_norm}, year={year}, "
            f"total chars={sum(len(t) for t in texts)}"
        )

    return texts


def fetch_official_pdf(
    bank: str,
    year: Optional[str] = None,
    use_playwright: bool = False,
) -> str:

    pdf_texts = fetch_official_pdfs(bank=bank, year=year, use_playwright=use_playwright)
    if not pdf_texts:
        return ""

    return "\n\n==== NEXT PDF ====\n\n".join(pdf_texts)