from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
DB_PATH = BASE_DIR / "predatory_journals.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_FILE = MODELS_DIR / "journal_classifier.joblib"
BERT_MODEL_DIR = MODELS_DIR / "bert_journal_classifier"
DATASET_PATH = BASE_DIR / "Predatory Journals Dataset.csv"

