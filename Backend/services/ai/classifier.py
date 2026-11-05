from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from models.ai_schemas import RouterIntentType


@dataclass(frozen=True)
class ClassifierPrediction:
    intent: RouterIntentType
    confidence: float
    abstain: bool
    backend_used: str


def _tokenize_ngrams(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9_]+", (text or "").casefold())
    tokens = list(words)
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]}_{words[i + 1]}")
    return tokens


class LocalIntentClassifier:
    """Optional local intent classifier evaluated for PR 6.

    Architectural boundary:
    - Only proposes `intent` (`RouterIntentType`) with a calibrated confidence score and `abstain` flag.
    - Never resolves entities, never checks permissions, and never calculates KPI numbers.
    - Uses `scikit-learn` (`TfidfVectorizer` + `LogisticRegression`) when installed in the environment,
      or falls back to an exact `numpy` TF-IDF + L2-regularized softmax classifier trained strictly on
      the `train` split of `ai_english_questions.json`.
    """

    def __init__(self, confidence_threshold: float = 0.72) -> None:
        self.confidence_threshold = confidence_threshold
        self.backend_used = "uninitialized"
        self._sklearn_pipeline: Any = None
        self._classes: list[str] = []
        self._vocab: dict[str, int] = {}
        self._idf: np.ndarray | None = None
        self._weights: np.ndarray | None = None
        self._bias: np.ndarray | None = None

    def fit(self, prompts: list[str], intents: list[str]) -> None:
        unique_classes = sorted(set(intents))
        self._classes = unique_classes

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-not-found]
            from sklearn.linear_model import LogisticRegression  # type: ignore[import-not-found]
            from sklearn.pipeline import Pipeline  # type: ignore[import-not-found]

            pipe = Pipeline(
                [
                    ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                    ("clf", LogisticRegression(C=2.0, max_iter=500, random_state=42)),
                ]
            )
            pipe.fit(prompts, intents)
            self._sklearn_pipeline = pipe
            self.backend_used = "scikit-learn"
            return
        except ImportError:
            pass

        # Deterministic numpy TF-IDF + L2-regularized multinomial logistic regression
        self.backend_used = "numpy-tfidf-l2-logreg"
        doc_tokens = [_tokenize_ngrams(p) for p in prompts]
        df_counter: Counter[str] = Counter()
        for toks in doc_tokens:
            for tok in set(toks):
                df_counter[tok] += 1

        vocab_list = sorted(df_counter.keys())
        self._vocab = {tok: idx for idx, tok in enumerate(vocab_list)}
        n_docs = len(prompts)
        n_vocab = len(vocab_list)
        n_classes = len(unique_classes)
        class_to_idx = {c: i for i, c in enumerate(unique_classes)}

        idf = np.zeros(n_vocab, dtype=np.float64)
        for tok, idx in self._vocab.items():
            idf[idx] = math.log((1.0 + n_docs) / (1.0 + df_counter[tok])) + 1.0
        self._idf = idf

        x_mat = np.zeros((n_docs, n_vocab), dtype=np.float64)
        for d_idx, toks in enumerate(doc_tokens):
            tf = Counter(toks)
            for tok, count in tf.items():
                v_idx = self._vocab.get(tok)
                if v_idx is not None:
                    x_mat[d_idx, v_idx] = (1.0 + math.log(count)) * idf[v_idx]
            norm = np.linalg.norm(x_mat[d_idx])
            if norm > 0:
                x_mat[d_idx] /= norm

        y_onehot = np.zeros((n_docs, n_classes), dtype=np.float64)
        for d_idx, label in enumerate(intents):
            y_onehot[d_idx, class_to_idx[label]] = 1.0

        w = np.zeros((n_vocab, n_classes), dtype=np.float64)
        b = np.zeros(n_classes, dtype=np.float64)
        lr = 0.8
        reg = 0.015
        for _ in range(350):
            logits = x_mat @ w + b
            logits -= np.max(logits, axis=1, keepdims=True)
            exp_l = np.exp(logits)
            probs = exp_l / np.sum(exp_l, axis=1, keepdims=True)
            diff = (probs - y_onehot) / n_docs
            grad_w = (x_mat.T @ diff) + reg * w
            grad_b = np.sum(diff, axis=0)
            w -= lr * grad_w
            b -= lr * grad_b

        self._weights = w
        self._bias = b

    def predict(self, prompt: str) -> ClassifierPrediction:
        if self._sklearn_pipeline is not None:
            probs = self._sklearn_pipeline.predict_proba([prompt])[0]
            best_idx = int(np.argmax(probs))
            best_conf = round(float(probs[best_idx]), 4)
            best_intent = str(self._sklearn_pipeline.classes_[best_idx])
            return ClassifierPrediction(
                intent=best_intent,  # type: ignore[arg-type]
                confidence=best_conf,
                abstain=best_conf < self.confidence_threshold,
                backend_used=self.backend_used,
            )

        if self._weights is None or self._bias is None or self._idf is None:
            return ClassifierPrediction(
                intent="current_value",
                confidence=0.0,
                abstain=True,
                backend_used=self.backend_used,
            )

        toks = _tokenize_ngrams(prompt)
        vec = np.zeros(len(self._vocab), dtype=np.float64)
        tf = Counter(toks)
        for tok, count in tf.items():
            v_idx = self._vocab.get(tok)
            if v_idx is not None:
                vec[v_idx] = (1.0 + math.log(count)) * self._idf[v_idx]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        logits = vec @ self._weights + self._bias
        logits -= np.max(logits)
        exp_l = np.exp(logits)
        probs = exp_l / np.sum(exp_l)
        best_idx = int(np.argmax(probs))
        best_conf = round(float(probs[best_idx]), 4)
        best_intent = self._classes[best_idx]
        return ClassifierPrediction(
            intent=best_intent,  # type: ignore[arg-type]
            confidence=best_conf,
            abstain=best_conf < self.confidence_threshold,
            backend_used=self.backend_used,
        )

    @classmethod
    def from_fixture_train_split(
        cls,
        fixture_path: Path | None = None,
        confidence_threshold: float = 0.72,
    ) -> LocalIntentClassifier:
        path = fixture_path or (
            Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai_english_questions.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        train_qs = [q for q in data["questions"] if q.get("split") == "train"]
        clf = cls(confidence_threshold=confidence_threshold)
        clf.fit(
            [q["prompt"] for q in train_qs],
            [q["expected_intent"] for q in train_qs],
        )
        return clf
