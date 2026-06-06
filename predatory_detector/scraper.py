from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urljoin

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


def get_internal_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links = []
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower()
    
    # Common journal subpage keywords
    keywords = ["editorial", "board", "fee", "charge", "apc", "about", "contact", "submit", "author", "price", "cost", "guideline"]
    
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        
        # Resolve relative URL
        full_url = urljoin(base_url, href)
        parsed_full = urlparse(full_url)
        
        # Must be same domain/subdomain
        if parsed_full.netloc.lower() == base_domain:
            path_lower = parsed_full.path.lower()
            text_lower = a_tag.get_text().lower()
            
            if any(kw in path_lower or kw in text_lower for kw in keywords):
                # Normalize url by stripping trailing slashes or queries
                normalized_url = full_url.split("?")[0].rstrip("/")
                if normalized_url not in links and normalized_url != base_url.split("?")[0].rstrip("/"):
                    links.append(normalized_url)
    return links


def scrape_journal(url: str) -> ScrapedJournal:
    html = fetch_html(url)
    title, description, body_text = extract_text(html)
    domain = urlparse(url).netloc
    
    soup = BeautifulSoup(html, "html.parser")
    internal_links = get_internal_links(soup, url)
    
    subpage_texts = []
    if internal_links:
        import concurrent.futures
        # Limit to up to 4 matched subpages
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_url = {executor.submit(fetch_html, link, timeout=5): link for link in internal_links[:4]}
            for future in concurrent.futures.as_completed(future_to_url):
                try:
                    subpage_html = future.result()
                    _, _, subpage_text = extract_text(subpage_html)
                    if subpage_text:
                        subpage_texts.append(subpage_text)
                except Exception:
                    pass
                    
    combined_text = body_text
    if subpage_texts:
        combined_text = body_text + " " + " ".join(subpage_texts)
        
    return ScrapedJournal(
        url=url,
        title=title,
        description=description,
        text=combined_text,
        domain=domain,
    )

