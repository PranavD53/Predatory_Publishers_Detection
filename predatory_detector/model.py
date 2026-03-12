from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from transformers import AutoModelForSequenceClassification, AutoTokenizer, TextClassificationPipeline

from .config import DATA_DIR, MODEL_FILE, BERT_MODEL_DIR
from .preprocess import build_input_text
from .scraper import scrape_journal


_MODEL_PIPELINE: Optional[Union[Pipeline, TextClassificationPipeline]] = None


@dataclass
class PredictionResult:
    label: str
    risk_score: float
    confidence: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "risk_score": float(self.risk_score),
            "confidence": float(self.confidence),
        }


def _default_training_data_path() -> Path:
    return DATA_DIR / "journals.csv"


def _bert_model_exists() -> bool:
    return BERT_MODEL_DIR.exists() and (BERT_MODEL_DIR / "config.json").exists()


def _load_bert_pipeline() -> TextClassificationPipeline:
    tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(BERT_MODEL_DIR)
    return TextClassificationPipeline(
        model=model,
        tokenizer=tokenizer,
        return_all_scores=True,
        truncation=True,
        padding=True,
        max_length=512,
    )


def load_or_train_model() -> Union[Pipeline, TextClassificationPipeline]:
    global _MODEL_PIPELINE

    if _MODEL_PIPELINE is not None:
        return _MODEL_PIPELINE

    # Prefer a fine-tuned BERT model if one has been trained.
    if _bert_model_exists():
        _MODEL_PIPELINE = _load_bert_pipeline()
        return _MODEL_PIPELINE

    if MODEL_FILE.exists():
        _MODEL_PIPELINE = joblib.load(MODEL_FILE)
        return _MODEL_PIPELINE

    csv_path = _default_training_data_path()
    if csv_path.exists():
        _MODEL_PIPELINE = train_from_csv(csv_path)
    else:
        _MODEL_PIPELINE = train_dummy_model()

    joblib.dump(_MODEL_PIPELINE, MODEL_FILE)
    return _MODEL_PIPELINE


def train_from_csv(csv_path: Path) -> Pipeline:
    df = pd.read_csv(csv_path)
    if not {"text", "label"}.issubset(df.columns):
        raise ValueError("Training CSV must contain 'text' and 'label' columns.")

    X = df["text"].astype(str)
    y = df["label"].astype(int)

    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 2))),
            ("clf", LogisticRegression(max_iter=200)),
        ]
    )

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_val)
    report = classification_report(y_val, y_pred)
    print("Validation report:\n", report)

    return pipeline


def train_dummy_model() -> Pipeline:
    texts = [
        "call for papers publish quickly low fees questionable peer review",
        "rapid publication journal without indexing spam email invitation",
        "international journal of innovative research impact factor fake",
        "well established journal indexed in scopus rigorous peer review",
        "official journal of professional association high publication ethics",
        "double blind peer review open access journal transparent policies",
    ]
    labels = [1, 1, 1, 0, 0, 0]  # 1 = predatory, 0 = legitimate

    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(max_features=3000, ngram_range=(1, 2))),
            ("clf", LogisticRegression(max_iter=200)),
        ]
    )
    pipeline.fit(texts, labels)
    return pipeline


def reload_model() -> Pipeline:
    global _MODEL_PIPELINE
    _MODEL_PIPELINE = None
    return load_or_train_model()


def predict_journal(url: str) -> Dict[str, Any]:
    pipeline = load_or_train_model()
    scraped = scrape_journal(url)
    input_text = build_input_text(scraped.title, scraped.description, scraped.text, scraped.domain)

    if isinstance(pipeline, TextClassificationPipeline):
        raw_output = pipeline(input_text)
        # Handle both shapes: [ {label, score}, ... ] and [ [ {label, score}, ... ] ]
        if isinstance(raw_output, list) and raw_output:
            first = raw_output[0]
            if isinstance(first, dict):
                scores = raw_output
            elif isinstance(first, list):
                scores = first
            else:
                raise ValueError(f"Unexpected BERT pipeline output element type: {type(first)}")
        else:
            raise ValueError(f"Unexpected BERT pipeline output type: {type(raw_output)}")

        # Expect labels like "LABEL_0" / "LABEL_1" or "Legitimate" / "Predatory"
        score_map = {s["label"]: float(s["score"]) for s in scores}
        predatory_score = None
        for key in score_map:
            lower = key.lower()
            if "pred" in lower or "1" in lower:
                predatory_score = score_map[key]
                break
        if predatory_score is None:
            predatory_score = float(scores[1]["score"]) if len(scores) > 1 else float(scores[0]["score"])
        risk_score = float(predatory_score)
        confidence = float(max(score_map.values()))
        label_str = "Predatory" if risk_score >= 0.5 else "Legitimate"
    else:
        probs = pipeline.predict_proba([input_text])[0]
        pred_label = int(np.argmax(probs))
        confidence = float(np.max(probs))
        risk_score = float(probs[1])  # probability of predatory class
        label_str = "Predatory" if pred_label == 1 else "Legitimate"

    result = PredictionResult(label=label_str, risk_score=risk_score, confidence=confidence)
    return {
        "url": url,
        "title": scraped.title,
        "description": scraped.description,
        "label": result.label,
        "risk_score": result.risk_score,
        "confidence": result.confidence,
    }

