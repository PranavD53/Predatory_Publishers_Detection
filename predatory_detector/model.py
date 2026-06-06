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

from .config import DATA_DIR, MODEL_FILE, BERT_MODEL_DIR
from .preprocess import build_input_text
from .scraper import scrape_journal


_MODEL_PIPELINE: Optional[Union[Pipeline, Any]] = None


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


def _load_bert_pipeline() -> Any:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, TextClassificationPipeline
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


def load_or_train_model() -> Union[Pipeline, Any]:
    global _MODEL_PIPELINE

    if _MODEL_PIPELINE is not None:
        return _MODEL_PIPELINE

    # Prefer a fine-tuned BERT model if one has been trained and we haven't forced the light model.
    import os
    force_light = os.environ.get("FORCE_LIGHT_MODEL", "false").lower() in ("true", "1", "yes")
    if _bert_model_exists() and not force_light:
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


def get_explainer_pipeline() -> Optional[Any]:
    try:
        if MODEL_FILE.exists():
            return joblib.load(MODEL_FILE)
    except Exception:
        pass
    return None


def extract_suspicious_phrases(text: str, pipeline: Any, top_n: int = 8) -> list[str]:
    # 1. Fallback list of high-priority predatory phrases
    predefined_keywords = [
        "rapid publication", "fast track review", "low fees", "open access journal of",
        "index copernicus", "fake impact factor", "scholarly scientific", "global impact factor",
        "waived fees", "innovative research", "unbeatable price", "publish quickly",
        "rapid peer review", "no publication fee", "low publication charge"
    ]
    
    matched = []
    text_lower = text.lower()
    for kw in predefined_keywords:
        if kw in text_lower:
            matched.append(kw)
            
    # 2. Extract high-coefficient n-grams if pipeline is available
    if pipeline and type(pipeline).__name__ != "TextClassificationPipeline":
        try:
            tfidf = pipeline.named_steps.get("tfidf")
            clf = pipeline.named_steps.get("clf")
            if tfidf and clf:
                feature_names = tfidf.get_feature_names_out()
                coefs = clf.coef_[0]
                
                # Transform the text to get TF-IDF weights
                X_text = tfidf.transform([text])
                nonzero_indices = X_text.nonzero()[1]
                
                features_with_weights = []
                for idx in nonzero_indices:
                    coef = coefs[idx]
                    # Class 1 is predatory, so positive coefficient means predatory
                    if coef > 0:
                        feature_name = feature_names[idx]
                        tfidf_val = X_text[0, idx]
                        score = coef * tfidf_val
                        features_with_weights.append((feature_name, score))
                
                features_with_weights.sort(key=lambda x: x[1], reverse=True)
                for feat, score in features_with_weights[:top_n]:
                    if feat not in matched:
                        matched.append(feat)
        except Exception:
            pass
            
    return matched[:top_n]


def predict_journal(url: str) -> Dict[str, Any]:
    pipeline = load_or_train_model()
    scraped = scrape_journal(url)
    input_text = build_input_text(scraped.title, scraped.description, scraped.text, scraped.domain)

    # Check class name to avoid importing transformers unless BERT is loaded.
    if type(pipeline).__name__ == "TextClassificationPipeline":
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

        # Some transformers versions ignore `return_all_scores=True` and only return
        # the top label. In that case, the score is confidence of that label, not
        # necessarily the "predatory probability".
        if len(scores) == 1:
            top_label = str(scores[0].get("label", "")).strip()
            top_score = float(scores[0].get("score", 0.0))
            lower = top_label.lower()
            if "pred" in lower or lower in {"label_1", "1"}:
                risk_score = top_score
                label_str = "Predatory"
            else:
                risk_score = 1.0 - top_score
                label_str = "Legitimate"
            confidence = top_score
        else:
            # Expect labels like "LABEL_0" / "LABEL_1" or "Legitimate" / "Predatory"
            score_map = {str(s["label"]): float(s["score"]) for s in scores}
            predatory_score = None
            for key in score_map:
                lower = key.lower()
                if "pred" in lower or lower in {"label_1", "1"}:
                    predatory_score = score_map[key]
                    break
            if predatory_score is None:
                # Fallback to second element if present, else first.
                predatory_score = float(scores[1]["score"]) if len(scores) > 1 else float(scores[0]["score"])
            risk_score = float(predatory_score)
            confidence = float(max(score_map.values())) if score_map else float(predatory_score)
            label_str = "Predatory" if risk_score >= 0.48 else "Legitimate"
    else:
        probs = pipeline.predict_proba([input_text])[0]
        confidence = float(np.max(probs))

        # NOTE: scikit-learn orders predict_proba columns by the estimator's `classes_`,
        # which is not guaranteed to be [0, 1]. We must map the "predatory" probability
        # from the correct column.
        clf = pipeline.named_steps.get("clf")
        classes = getattr(clf, "classes_", None)
        if classes is None:
            # Fallback: assume conventional binary ordering [0, 1]
            predatory_idx = 1 if len(probs) > 1 else 0
        else:
            classes = list(classes)
            if 1 in classes:
                predatory_idx = classes.index(1)
            else:
                # If trained with string labels, try common variants.
                lowered = [str(c).lower() for c in classes]
                predatory_idx = next(
                    (i for i, c in enumerate(lowered) if "pred" in c or c in {"1", "true", "yes"}),
                    1 if len(probs) > 1 else 0,
                )

        risk_score = float(probs[predatory_idx])
        label_str = "Predatory" if risk_score >= 0.5 else "Legitimate"

    result = PredictionResult(label=label_str, risk_score=risk_score, confidence=confidence)
    
    explainer_pipeline = pipeline if type(pipeline).__name__ != "TextClassificationPipeline" else get_explainer_pipeline()
    suspicious_phrases = extract_suspicious_phrases(input_text, explainer_pipeline)
    
    return {
        "url": url,
        "title": scraped.title,
        "description": scraped.description,
        "label": result.label,
        "risk_score": result.risk_score,
        "confidence": result.confidence,
        "suspicious_phrases": suspicious_phrases,
    }

