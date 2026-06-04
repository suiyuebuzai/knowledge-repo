"""
Knowledge MCP Server

非结构化文档检索，通过 MCP 协议暴露给 Claude。

启动方式（SSE 模式）：
    C:/1AI/.pvenv/Scripts/python.exe server.py
    -> 默认监听 http://localhost:8001/sse

环境变量：
    KNOWLEDGE_SERVER_PORT  服务端口，默认 8001
    ANTHROPIC_AUTH_TOKEN   Claude API key（ask_document 工具使用）
    ANTHROPIC_BASE_URL     公司代理地址
"""
import json
import os

import anthropic
from mcp.server.fastmcp import FastMCP

import config
import retriever
import bm25_store

# 启动时从 ChromaDB 重建 BM25 索引
bm25_store.rebuild_from_chroma()

_port = int(os.environ.get("KNOWLEDGE_SERVER_PORT", "8001"))
mcp = FastMCP("knowledge", port=_port)


@mcp.tool()
def search_documents(query: str, top_k: int = 5) -> str:
    """
    在本地知识库中语义检索相关文档片段，返回原始片段供 Claude 综合回答。
    当用户需要查找文档内容、了解某个主题时使用。

    Args:
        query:  检索关键词或问题。示例: "合同有效期条款" / "年假申请流程"
        top_k:  返回最相关片段数，默认 5，最大 20

    Returns:
        JSON 字符串，包含:
          query    原始查询词
          results  列表，每项有:
            text    文档片段原文
            source  来源文件名（如 "合同模板.pdf"）
            score   相似度（0~1，越高越相关）
    """
    try:
        results = retriever.search(query, min(top_k, 20))
        return json.dumps({"query": query, "results": results}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def ask_document(question: str) -> str:
    """
    在知识库中检索相关片段，由 Claude 直接综合回答问题。
    当用户提出需要理解文档内容才能回答的问题时使用。

    Args:
        question: 自然语言问题。示例: "合同到期后如何续签？" / "年假政策是什么？"

    Returns:
        基于文档内容的答案字符串。知识库为空时提示先运行 ingest.py。
    """
    try:
        chunks = retriever.search(question, top_k=config.TOP_K)
        if not chunks:
            return "知识库中未找到相关内容，请先运行 python ingest.py 索引文档。"

        context = "\n\n".join(
            f"[{i+1}] 来源：{c['source']}\n{c['text']}"
            for i, c in enumerate(chunks)
        )
        prompt = (
            "根据以下文档片段回答问题，只使用片段中的信息，"
            "如片段中没有答案请明确说明。\n\n"
            f"{context}\n\n"
            f"问题：{question}"
        )

        client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
            base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        )
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    except Exception as e:
        # 降级：返回原始片段，不抛出异常
        try:
            chunks = retriever.search(question, top_k=config.TOP_K)
            fallback = "\n\n".join(
                f"[{i+1}] {c['source']}: {c['text']}"
                for i, c in enumerate(chunks)
            )
            return f"生成失败（{e}），原始片段如下：\n\n{fallback}"
        except Exception:
            return f"服务错误：{e}"


if __name__ == "__main__":
    mcp.run(transport="sse")
