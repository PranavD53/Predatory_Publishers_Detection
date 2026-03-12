from __future__ import annotations

import re
from typing import Iterable, List


URL_RE = re.compile(r"https?://\S+")
WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    text = text.lower()
    text = URL_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def combine_fields(fields: Iterable[str]) -> str:
    return " ".join(f for f in fields if f).strip()


def build_input_text(title: str, description: str, body: str, domain: str) -> str:
    raw = f"{title} {description} {body} {domain}"
    return clean_text(raw)

