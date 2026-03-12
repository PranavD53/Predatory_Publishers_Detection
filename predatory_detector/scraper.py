from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


@dataclass
class ScrapedJournal:
    url: str
    title: str
    description: str
    text: str
    domain: str


def fetch_html(url: str, timeout: int = 10) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def extract_text(html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.text.strip() if soup.title else ""

    description_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    description = description_tag["content"].strip() if description_tag and description_tag.get("content") else ""

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    body_text = " ".join(chunk.strip() for chunk in soup.get_text(separator=" ").split())

    return title, description, body_text


def scrape_journal(url: str) -> ScrapedJournal:
    html = fetch_html(url)
    title, description, body_text = extract_text(html)
    domain = urlparse(url).netloc
    return ScrapedJournal(
        url=url,
        title=title,
        description=description,
        text=body_text,
        domain=domain,
    )

