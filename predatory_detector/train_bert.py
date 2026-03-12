from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

from .config import BASE_DIR, BERT_MODEL_DIR, DATASET_PATH


@dataclass
class JournalDataset(Dataset):
    encodings: dict
    labels: np.ndarray

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int):
        item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item


def _infer_columns(df: pd.DataFrame) -> Tuple[str, str]:
    lower_cols = {c.lower(): c for c in df.columns}

    # Label column: anything that looks like a class/target/predatory flag.
    label_candidates = [
        name
        for key, name in lower_cols.items()
        if any(tok in key for tok in ["label", "predatory", "is_predatory", "target", "class"])
    ]
    if not label_candidates:
        raise ValueError("Could not infer label column; expected something like 'label' or 'predatory'.")
    label_col = label_candidates[0]

    # Text column: look for text/description/content/abstract/journal/title.
    text_order = [
        "text",
        "clean_text",
        "description",
        "abstract",
        "content",
        "journal",
        "title",
    ]
    text_col = None
    for key in text_order:
        for col_lower, orig in lower_cols.items():
            if key in col_lower:
                text_col = orig
                break
        if text_col:
            break
    if text_col is None:
        raise ValueError("Could not infer text column; expected something like 'text' or 'description'.")

    return text_col, label_col


def _prepare_labels(raw: pd.Series) -> np.ndarray:
    if np.issubdtype(raw.dtype, np.number):
        vals = raw.astype(int).values
        unique = sorted(set(vals))
        if unique == [0, 1]:
            return vals
        raise ValueError("Numeric labels must be encoded as 0/1.")

    lower = raw.astype(str).str.lower()
    mapping = {"predatory": 1, "legitimate": 0, "legit": 0, "non-predatory": 0}
    mapped = lower.map(lambda v: mapping.get(v))
    if mapped.isnull().any():
        raise ValueError("String labels must map to 'Predatory' or 'Legitimate'.")
    return mapped.astype(int).values


def main() -> None:
    if not DATASET_PATH.exists():
        raise SystemExit(f"Expected dataset at {DATASET_PATH}, but file was not found.")

    df = pd.read_csv(DATASET_PATH)
    text_col, label_col = _infer_columns(df)

    texts = df[text_col].astype(str).tolist()
    labels = _prepare_labels(df[label_col])

    model_name = "distilbert-base-uncased"
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    encodings = tokenizer(texts, truncation=True, padding=True, max_length=256)
    dataset = JournalDataset(encodings=encodings, labels=labels)

    num_labels = 2
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=num_labels,
        id2label={0: "Legitimate", 1: "Predatory"},
        label2id={"Legitimate": 0, "Predatory": 1},
    )

    training_args = TrainingArguments(
        output_dir=str(BERT_MODEL_DIR),
        num_train_epochs=2,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        learning_rate=5e-5,
        weight_decay=0.01,
        logging_steps=50,
        save_strategy="epoch",
        load_best_model_at_end=False,
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
    )

    trainer.train()

    BERT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(BERT_MODEL_DIR)
    tokenizer.save_pretrained(BERT_MODEL_DIR)
    print(f"Saved fine-tuned BERT model to {BERT_MODEL_DIR}")


if __name__ == "__main__":
    main()

