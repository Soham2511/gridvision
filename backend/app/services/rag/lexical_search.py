"""Lexical BM25 Search for Regulatory Standards and Exact Technical Identifiers.

Implements Okapi BM25 scoring with exact regulatory identifier boosting (e.g. IS 732,
ISEER, BEE Star Ratings, CEA Baseline) to ensure exact clause numbers and terms
score at the top of retrieval results.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Set, Tuple


class BM25Index:
    """Okapi BM25 index supporting incremental document additions and exact-code boosting."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_ids: List[str] = []
        self.doc_lengths: Dict[str, int] = {}
        self.doc_tokens: Dict[str, List[str]] = {}
        self.term_doc_freqs: Dict[str, int] = {}
        self.total_docs: int = 0
        self.avg_doc_len: float = 0.0

        # Exact regulatory codes to heavily weight when present in query and document
        self.REGULATORY_CODES: Set[str] = {
            "is-732",
            "is732",
            "is-1391",
            "is1391",
            "nec",
            "bee",
            "cea",
            "discom",
            "iseer",
            "lpd",
            "myt",
            "kwh",
            "kva",
            "star",
        }

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text preserving alphanumeric codes, dashes, and periods."""
        clean = text.lower()
        # Find explicit code patterns like IS 732, IS-732, Clause 4.1
        clean = re.sub(r"is\s+(\d+)", r"is-\1", clean)
        clean = re.sub(r"clause\s+(\d+(?:\.\d+)?)", r"clause-\1", clean)
        raw_tokens = re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", clean)
        return [t for t in raw_tokens if len(t) > 1 or t.isdigit()]

    def add_document(self, doc_id: str, text: str) -> None:
        """Add or update a document in the BM25 index."""
        if doc_id in self.doc_tokens:
            self.remove_document(doc_id)

        tokens = self._tokenize(text)
        self.doc_ids.append(doc_id)
        self.doc_lengths[doc_id] = len(tokens)
        self.doc_tokens[doc_id] = tokens
        self.total_docs += 1

        # Track unique terms in this doc
        unique_terms = set(tokens)
        for term in unique_terms:
            self.term_doc_freqs[term] = self.term_doc_freqs.get(term, 0) + 1

        self.avg_doc_len = sum(self.doc_lengths.values()) / max(1, self.total_docs)

    def remove_document(self, doc_id: str) -> None:
        """Remove a document from the BM25 index."""
        if doc_id not in self.doc_tokens:
            return
        tokens = self.doc_tokens.pop(doc_id)
        self.doc_lengths.pop(doc_id, None)
        if doc_id in self.doc_ids:
            self.doc_ids.remove(doc_id)
        self.total_docs = max(0, self.total_docs - 1)

        unique_terms = set(tokens)
        for term in unique_terms:
            if term in self.term_doc_freqs:
                self.term_doc_freqs[term] -= 1
                if self.term_doc_freqs[term] <= 0:
                    del self.term_doc_freqs[term]

        self.avg_doc_len = (
            sum(self.doc_lengths.values()) / max(1, self.total_docs)
            if self.total_docs > 0
            else 0.0
        )

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search index and return list of (doc_id, bm25_score) tuples."""
        if self.total_docs == 0:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: Dict[str, float] = {}

        for q_token in query_tokens:
            df = self.term_doc_freqs.get(q_token, 0)
            if df == 0:
                continue

            # Standard BM25 Robertson-Spärck Jones IDF
            idf = math.log(1.0 + (self.total_docs - df + 0.5) / (df + 0.5))

            # Code boost multiplier
            boost = 3.0 if q_token in self.REGULATORY_CODES or "clause" in q_token or "is-" in q_token else 1.0

            for doc_id, tokens in self.doc_tokens.items():
                # Count term occurrences in doc
                tf = tokens.count(q_token)
                if tf == 0:
                    continue

                doc_len = self.doc_lengths.get(doc_id, 1)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / max(1e-6, self.avg_doc_len)))
                score_part = idf * (tf * (self.k1 + 1.0) / denom) * boost
                scores[doc_id] = scores.get(doc_id, 0.0) + score_part

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

