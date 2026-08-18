"""检索层单元测试：分词 / 相关性 / 边界。"""

from __future__ import annotations

from pathlib import Path

from app.retrieval.store import InMemoryStore, chunk_text, load_kb, tokenize


def test_tokenize_handles_cjk_and_ascii():
    assert tokenize("退货Policy v2") == ["退", "货", "policy", "v2"]


def test_chunk_text_packs_paragraphs():
    text = "第一段。\n\n第二段。\n\n第三段。"
    chunks = chunk_text(text, target_chars=8)
    assert len(chunks) >= 2
    assert all(chunks)


def test_search_ranks_relevant_doc_first():
    store = InMemoryStore()
    store.add("退货政策", "自签收之日起 7 天内支持无理由退货，运费由买家承担。")
    store.add("会员体系", "会员分为银卡、金卡、钻石卡三个等级。")

    hits = store.search("退货运费谁出", k=2)
    assert hits[0]["doc_id"] == "退货政策"
    assert hits[0]["score"] > 0


def test_search_empty_store_and_no_overlap():
    empty = InMemoryStore()
    assert empty.search("任意问题") == []

    store = InMemoryStore()
    store.add("退货政策", "退货相关内容")
    assert store.search("量子力学") == []


def test_load_kb_from_sample():
    store = load_kb(Path("data/sample_kb.md"))
    assert "退货政策" in store.doc_ids()
    assert store.get_text("退货政策") and "7 天" in store.get_text("退货政策")
