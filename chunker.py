from pathlib import Path
import config


def _chunk_text(text: str, source: str) -> list[dict]:
    """将文本按 CHUNK_SIZE/OVERLAP 分块。"""
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + config.CHUNK_SIZE
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "id": f"{source}#{idx}",
                "text": chunk_text,
                "metadata": {"source": source, "page": 0},
            })
            idx += 1
        start += config.CHUNK_SIZE - config.CHUNK_OVERLAP
    return chunks


def _load_txt(file_path: str) -> str:
    with open(file_path, encoding="utf-8") as f:
        return f.read()


def _load_pdf(file_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _load_docx(file_path: str) -> str:
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def load_and_chunk(file_path: str) -> list[dict]:
    """解析文档并分块。支持 .pdf / .docx / .txt。"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    source = path.name

    if suffix == ".txt":
        text = _load_txt(file_path)
    elif suffix == ".pdf":
        text = _load_pdf(file_path)
    elif suffix == ".docx":
        text = _load_docx(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}（仅支持 .pdf / .docx / .txt）")

    return _chunk_text(text, source)
