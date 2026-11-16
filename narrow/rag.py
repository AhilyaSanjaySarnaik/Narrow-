"""Hybrid retrieval over a local Markdown knowledge base."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class Passage:
    id: str
    text: str
    score: float


class KnowledgeBase:
    def __init__(
        self,
        root: str | Path = "kb",
        model_path: str | Path = "models/bge-small-en-v1.5",
        abstain_threshold: float = 0.35,
    ) -> None:
        self.root = Path(root)
        self.model_path = Path(model_path)
        self.abstain_threshold = abstain_threshold
        self.passages = self._load_passages()
        self._encoder: Any | None = None
        self._embeddings: Any | None = None
        self._tokens = [_TOKEN.findall(passage.text.lower()) for passage in self.passages]

    def _load_passages(self) -> list[Passage]:
        passages: list[Passage] = []
        if not self.root.exists():
            return passages
        for path in sorted(self.root.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            doc_id = path.relative_to(self.root).with_suffix("").as_posix()
            section = "intro"
            body: list[str] = []

            def flush() -> None:
                content = "\n".join(body).strip()
                if content:
                    passages.append(Passage(f"{doc_id}#{section}", content, 0.0))

            for line in text.splitlines():
                match = _HEADING.match(line)
                if match:
                    flush()
                    section = re.sub(r"[^a-z0-9]+", "-", match.group(2).lower()).strip("-") or "section"
                    body = [line]
                else:
                    body.append(line)
            flush()
        return passages

    def _load_encoder(self) -> Any:
        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError("Install the project dependencies to enable dense retrieval.") from exc
            if not self.model_path.exists():
                raise FileNotFoundError(f"Local embedding model not found: {self.model_path}")
            self._encoder = SentenceTransformer(str(self.model_path), local_files_only=True)
        return self._encoder

    @staticmethod
    def _bm25(query_tokens: list[str], documents: list[list[str]]) -> list[float]:
        if not documents:
            return []
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise RuntimeError("Install the project dependencies to enable BM25 retrieval.") from exc
        return [float(score) for score in BM25Okapi(documents).get_scores(query_tokens)]

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if not self.passages:
            return {"passages": [], "abstain": True}
        query_tokens = _TOKEN.findall(query.lower())
        bm25_scores = self._bm25(query_tokens, self._tokens)
        bm25_max = max(bm25_scores, default=0.0) or 1.0
        bm25_normalized = [score / bm25_max for score in bm25_scores]

        encoder = self._load_encoder()
        if self._embeddings is None:
            self._embeddings = encoder.encode(
                [passage.text for passage in self.passages],
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        query_embedding = encoder.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        dense_scores = [float(value) for value in self._embeddings @ query_embedding]
        dense_normalized = [max(0.0, min(1.0, (score + 1.0) / 2.0)) for score in dense_scores]

        results: list[Passage] = []
        for index, passage in enumerate(self.passages):
            score = 0.5 * bm25_normalized[index] + 0.5 * dense_normalized[index]
            results.append(Passage(passage.id, passage.text, score))
        results.sort(key=lambda item: item.score, reverse=True)
        selected = results[:limit]
        return {
            "passages": [item.__dict__ for item in selected],
            "abstain": not selected or selected[0].score < self.abstain_threshold,
        }
