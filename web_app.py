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
import bm25_store

# 启动时从 ChromaDB 重建 BM25 索引
bm25_store.rebuild_from_chroma()

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


# ── 图谱路由 ──
from graph import graph_manager
from graph import query as graph_query

# 启动时自动从缓存加载图（有缓存则加载，无缓存则跳过）
graph_manager.load_from_cache()


@app.get("/graph")
async def graph_page(request: Request):
    return templates.TemplateResponse(request, "graph.html", {
        "loaded": graph_manager.is_loaded,
    })


@app.get("/graph/api/search")
async def graph_search(q: str = ""):
    G = graph_manager.get_graph()
    if G is None:
        return {"error": "图数据未加载，请点击刷新数据"}
    results = graph_query.search_person(G, q.strip()) if q.strip() else []
    return {"results": results}


@app.get("/graph/api/neighbors")
async def graph_neighbors(id: str, depth: int = 2):
    G = graph_manager.get_graph()
    if G is None:
        return {"error": "图数据未加载，请点击刷新数据"}
    return graph_query.get_neighbors(G, id, depth)


@app.get("/graph/api/chain")
async def graph_chain(id: str, direction: str = "up"):
    G = graph_manager.get_graph()
    if G is None:
        return {"error": "图数据未加载，请点击刷新数据"}
    if direction == "up":
        return {"chain": graph_query.get_superior_chain(G, id)}
    else:
        return {"subordinates": graph_query.get_subordinates(G, id, depth=10)}


@app.get("/graph/api/path")
async def graph_path(source: str, target: str):
    G = graph_manager.get_graph()
    if G is None:
        return {"error": "图数据未加载，请点击刷新数据"}
    path = graph_query.find_path(G, source, target)
    common = graph_query.find_common_superior(G, source, target)
    return {"path": path, "common_superior": common}


@app.get("/graph/api/dept")
async def graph_dept(name: str = "", no: str = "", sap: str = ""):
    G = graph_manager.get_graph()
    if G is None:
        return {"error": "图数据未加载，请先在「检索」页面刷新数据"}
    if no:
        return {"members": graph_query.get_dept_members_by_no(G, no, sap)}
    return {"members": graph_query.get_dept_members(G, name)}


@app.get("/graph/api/stats")
async def graph_stats():
    G = graph_manager.get_graph()
    if G is None:
        return {"error": "图数据未加载，请点击刷新数据"}
    return graph_query.get_stats(G)


@app.post("/graph/api/refresh")
async def graph_refresh():
    G = graph_manager.refresh()
    return {"status": "ok", "stats": graph_query.get_stats(G)}


from graph.dept_loader import dept_manager

# 启动时从缓存加载部门数据
dept_manager.load_from_cache()


@app.get("/graph/dept-tree")
async def dept_tree_page(request: Request):
    return templates.TemplateResponse(request, "dept_tree.html", {
        "loaded": dept_manager.is_loaded,
    })


@app.get("/graph/api/dept-tree")
async def dept_tree_data():
    tree = dept_manager.get_tree()
    if tree is None:
        return {"error": "部门数据未加载，请点击刷新数据"}
    return tree


@app.post("/graph/api/dept-tree/refresh")
async def dept_tree_refresh():
    tree = dept_manager.refresh()
    n_div = len(tree.get("children", []))
    n_dept = sum(len(n.get("children", [])) for n in tree["children"])
    return {"status": "ok", "divisions": n_div, "departments": n_dept}


from graph.nl_query import ask as graph_ask


@app.get("/graph/ask")
async def graph_ask_page(request: Request):
    return templates.TemplateResponse(request, "graph_ask.html")


@app.get("/graph/api/ask")
async def graph_nl_ask(q: str = ""):
    if not q.strip():
        return {"answer": "请输入问题"}
    G = graph_manager.get_graph()
    if G is None:
        return {"error": "图数据未加载，请点击刷新数据"}
    try:
        answer = graph_ask(q.strip(), G)
        return {"answer": answer}
    except Exception as e:
        return {"error": f"问答失败: {e}"}


# ── 找文档路由 ──
from ingest import find_documents, _fmt_size as _find_fmt_size
from datetime import datetime as _dt


@app.get("/find")
async def find_page(request: Request):
    return templates.TemplateResponse(request, "find.html", {
        "default_dir": config.DOCS_DIR,
    })


@app.get("/find/api/scan")
async def find_scan(
    dir: str = config.DOCS_DIR,
    query: str = "",
    ext: str = ".pdf,.docx,.txt,.md",
    recursive: bool = True,
):
    root = Path(dir)
    if not root.exists():
        return {"error": f"目录不存在：{dir}"}
    if not root.is_dir():
        return {"error": f"路径不是目录：{dir}"}

    extensions = {e.strip() for e in ext.split(",") if e.strip()}
    files = find_documents(
        root_dir=dir,
        extensions=extensions,
        query=query or None,
        recursive=recursive,
    )

    root_resolved = root.resolve()
    result = []
    for f in files:
        try:
            stat = f.stat()
            try:
                rel = str(f.relative_to(root_resolved))
            except ValueError:
                rel = str(f)
            result.append({
                "name": f.name,
                "ext": f.suffix.upper(),
                "size": _find_fmt_size(stat.st_size),
                "mtime": _dt.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                "rel_path": rel,
                "abs_path": str(f),
            })
        except Exception:
            continue

    return {"total": len(result), "files": result}


@app.post("/find/api/index")
async def find_index(request: Request):
    body = await request.json()
    file_paths = body.get("files", [])

    def generate():
        total = len(file_paths)
        success = 0
        failed = 0
        for abs_path in file_paths:
            fname = Path(abs_path).name
            yield f"data: {json.dumps({'file': fname, 'status': 'indexing'}, ensure_ascii=False)}\n\n"
            try:
                chunks = chunker.load_and_chunk(abs_path)
                texts = [c["text"] for c in chunks]
                embeddings = embedder.embed(texts)
                store.upsert(chunks, embeddings)
                success += 1
                yield f"data: {json.dumps({'file': fname, 'status': 'done', 'chunks': len(chunks)}, ensure_ascii=False)}\n\n"
            except Exception as e:
                failed += 1
                yield f"data: {json.dumps({'file': fname, 'status': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps({'total': total, 'success': success, 'failed': failed}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("KNOWLEDGE_WEB_PORT", config.WEB_PORT))
    uvicorn.run(app, host="0.0.0.0", port=port)
