"""
Knowledge Web App

浏览器访问本地知识库：问答、检索、上传文档。

启动：
    C:/1AI/.pvenv/Scripts/python.exe web_app.py
    -> http://localhost:8080
"""
import os
import sys
from pathlib import Path

# 确保能 import 同目录模块
sys.path.insert(0, str(Path(__file__).parent))

import json

import anthropic
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import retriever
import chunker
import embedder
import store

app = FastAPI(title="Knowledge Web")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/")
async def ask_page(request: Request):
    return templates.TemplateResponse(request, "ask.html")


@app.get("/ask/stream")
async def ask_stream(q: str = ""):
    if not q.strip():
        return StreamingResponse(
            iter(["data: 请输入问题\n\n", "event: done\ndata: [DONE]\n\n"]),
            media_type="text/event-stream",
        )

    def generate():
        chunks = retriever.search(q.strip(), top_k=config.TOP_K)
        if not chunks:
            yield "data: 知识库中未找到相关内容，请先上传文档。\n\n"
            yield "event: done\ndata: [DONE]\n\n"
            return

        context = "\n\n".join(
            f"[{i+1}] 来源：{c['source']}\n{c['text']}"
            for i, c in enumerate(chunks)
        )
        prompt = (
            "根据以下文档片段回答问题，只使用片段中的信息，"
            "如片段中没有答案请明确说明。\n\n"
            f"{context}\n\n"
            f"问题：{q.strip()}"
        )

        try:
            client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
                base_url=os.environ.get("ANTHROPIC_BASE_URL"),
            )
            with client.messages.stream(
                model=config.CLAUDE_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {text}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

        sources = [{"source": c["source"], "score": c["score"]} for c in chunks]
        yield f"event: sources\ndata: {json.dumps(sources, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/search")
async def search_page(request: Request, q: str = ""):
    results = []
    if q.strip():
        results = retriever.search(q.strip(), top_k=10)
    return templates.TemplateResponse(request, "search.html", {"query": q, "results": results})


@app.get("/upload")
async def upload_page(request: Request, msg: str = "", error: str = ""):
    indexed_files = []
    try:
        col = store._get_collection()
        if col.count() > 0:
            all_meta = col.get(include=["metadatas"])["metadatas"]
            file_chunks = {}
            for meta in all_meta:
                src = meta.get("source", "unknown")
                file_chunks[src] = file_chunks.get(src, 0) + 1
            indexed_files = [{"name": k, "chunks": v} for k, v in sorted(file_chunks.items())]
    except Exception:
        pass
    return templates.TemplateResponse(request, "upload.html", {
        "msg": msg,
        "error": error,
        "indexed_files": indexed_files,
    })


@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    if not files or not files[0].filename:
        return RedirectResponse("/upload?error=请选择文件", status_code=303)

    results = []
    errors = []
    docs_dir = Path(config.DOCS_DIR)

    for file in files:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in {".pdf", ".docx", ".txt"}:
            errors.append(f"{file.filename}: 不支持的格式")
            continue

        dest = docs_dir / file.filename
        content = await file.read()
        dest.write_bytes(content)

        try:
            chunks = chunker.load_and_chunk(str(dest))
            texts = [c["text"] for c in chunks]
            embeddings = embedder.embed(texts)
            store.upsert(chunks, embeddings)
            results.append(f"{file.filename}: {len(chunks)} 个片段已索引")
        except Exception as e:
            errors.append(f"{file.filename}: {e}")

    msg = "; ".join(results) if results else ""
    error = "; ".join(errors) if errors else ""
    return RedirectResponse(f"/upload?msg={msg}&error={error}", status_code=303)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("KNOWLEDGE_WEB_PORT", config.WEB_PORT))
    uvicorn.run(app, host="0.0.0.0", port=port)
