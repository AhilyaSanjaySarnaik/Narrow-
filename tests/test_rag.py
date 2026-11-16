from narrow.rag import KnowledgeBase


class _Embeddings:
    def __init__(self, rows):
        self.rows = rows

    def __matmul__(self, vector):
        return [sum(left * right for left, right in zip(row, vector)) for row in self.rows]


class _Encoder:
    def encode(self, texts, **_kwargs):
        if texts[0].lower() in {"access control", "unrelated"}:
            vector = [1.0, 0.0] if "access" in texts[0].lower() else [0.0, 1.0]
            return [vector]
        return _Embeddings([[1.0, 0.0]] * len(texts))


def test_markdown_is_chunked_by_heading_with_stable_ids(tmp_path):
    root = tmp_path / "kb"
    root.mkdir()
    (root / "guide.md").write_text(
        "# Overview\nIntro.\n\n## Access Control\nLeast privilege.", encoding="utf-8"
    )

    kb = KnowledgeBase(root=root)

    assert [passage.id for passage in kb.passages] == [
        "guide#overview",
        "guide#access-control",
    ]
    assert kb.passages[1].text.endswith("Least privilege.")


def test_empty_kb_abstains_without_loading_models(tmp_path):
    kb = KnowledgeBase(root=tmp_path / "missing", model_path=tmp_path / "model")
    assert kb.search("anything") == {"passages": [], "abstain": True}


def test_search_combines_keyword_and_dense_scores(tmp_path, monkeypatch):
    root = tmp_path / "kb"
    root.mkdir()
    (root / "guide.md").write_text(
        "# Access\nUse least privilege.\n\n# Backups\nTest restoration.",
        encoding="utf-8",
    )
    monkeypatch.setattr(KnowledgeBase, "_load_encoder", lambda self: _Encoder())
    monkeypatch.setattr(
        KnowledgeBase,
        "_bm25",
        staticmethod(lambda _query, documents: [1.0 if "access" in doc else 0.0 for doc in documents]),
    )

    result = KnowledgeBase(root=root).search("access control", limit=1)

    assert result["abstain"] is False
    assert result["passages"][0]["id"] == "guide#access"


def test_search_abstains_when_best_score_is_below_threshold(tmp_path, monkeypatch):
    root = tmp_path / "kb"
    root.mkdir()
    (root / "guide.md").write_text("# Access\nUse least privilege.", encoding="utf-8")
    monkeypatch.setattr(KnowledgeBase, "_load_encoder", lambda self: _Encoder())
    monkeypatch.setattr(KnowledgeBase, "_bm25", staticmethod(lambda _query, documents: [0.0]))

    result = KnowledgeBase(root=root, abstain_threshold=0.99).search("unrelated", limit=1)

    assert result["abstain"] is True
