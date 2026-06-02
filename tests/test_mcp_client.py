"""
通过 MCP 协议测试 knowledge-server 的两个工具：
  - search_documents
  - ask_document

前提：先启动 server
    C:/1AI/.pvenv/Scripts/python.exe server.py

用法：
    C:/1AI/.pvenv/Scripts/python.exe test_mcp_client.py
"""
import asyncio
import json

from mcp import ClientSession
from mcp.client.sse import sse_client

SERVER_URL = "http://localhost:8001/sse"


async def run_tests():
    print(f"连接 knowledge-server（SSE）: {SERVER_URL}")
    async with sse_client(SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("已连接\n")

            # ── 列出工具 ────────────────────────────────────────────
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"可用工具: {tool_names}\n")

            # ── 测试 search_documents ────────────────────────────────
            print("=" * 55)
            print("TEST 1: search_documents")
            print("=" * 55)

            for query in ["财务", "attention mechanism", "合同"]:
                print(f"\n  query: {query!r}")
                result = await session.call_tool(
                    "search_documents",
                    {"query": query, "top_k": 3},
                )
                if result.isError:
                    print(f"  [ERROR] {result.content}")
                    continue

                data = json.loads(result.content[0].text)
                for i, r in enumerate(data.get("results", []), 1):
                    text_preview = r["text"][:70].replace("\n", " ")
                    print(f"  [{i}] score={r.get('score', 0):.3f}  src={r['source']}")
                    print(f"       {text_preview}...")

            # ── 测试 ask_document ────────────────────────────────────
            print()
            print("=" * 55)
            print("TEST 2: ask_document")
            print("=" * 55)

            question = "财务标准价格估算数字人这份文档的主要内容是什么？"
            print(f"\n  question: {question!r}")
            print("  （ask_document 内部调用 Claude，稍等...）\n")

            result = await session.call_tool(
                "ask_document",
                {"question": question},
            )
            if result.isError:
                print(f"  [ERROR] {result.content}")
            else:
                print(result.content[0].text)

    print("\n[OK] 测试完成")


if __name__ == "__main__":
    asyncio.run(run_tests())
