import pytest
from pathlib import Path
import chunker
import config


def test_chunk_text_basic():
    """短文本应产生 1 个 chunk。"""
    chunks = chunker._chunk_text("Python 是一种编程语言。", source="test.txt")
    assert len(chunks) == 1
    assert chunks[0]["text"] == "Python 是一种编程语言。"
    assert chunks[0]["metadata"]["source"] == "test.txt"


def test_chunk_text_splits_long_text(monkeypatch):
    """超过 CHUNK_SIZE 的文本应拆分为多个 chunk。"""
    monkeypatch.setattr(config, "CHUNK_SIZE", 10)
    monkeypatch.setattr(config, "CHUNK_OVERLAP", 2)
    text = "A" * 25
    chunks = chunker._chunk_text(text, source="long.txt")
    assert len(chunks) > 1
    assert all(c["metadata"]["source"] == "long.txt" for c in chunks)


def test_chunk_ids_are_unique():
    text = "X" * 600
    chunks = chunker._chunk_text(text, source="dup.txt")
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))


def test_load_and_chunk_txt(tmp_path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("这是第一段内容。\n这是第二段内容。", encoding="utf-8")
    chunks = chunker.load_and_chunk(str(txt_file))
    assert len(chunks) >= 1
    assert chunks[0]["metadata"]["source"] == "sample.txt"
    full_text = " ".join(c["text"] for c in chunks)
    assert "第一段" in full_text


def test_load_and_chunk_unsupported_format(tmp_path):
    bad_file = tmp_path / "file.xyz"
    bad_file.write_text("content")
    with pytest.raises(ValueError, match="不支持的文件格式"):
        chunker.load_and_chunk(str(bad_file))
