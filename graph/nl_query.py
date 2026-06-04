# knowledge-server/graph/nl_query.py
"""
自然语言图谱问答。

使用 Claude function calling：将图查询函数暴露为工具，
LLM 根据用户问题自动决定调用哪个函数，执行后生成自然语言答案。
"""
import json
import os
import sys
import time
import anthropic
import networkx as nx

import config
from graph import query as graph_query
from graph.dept_loader import dept_manager

TOOLS = [
    {
        "name": "search_person",
        "description": "根据姓名、工号或英文名模糊搜索人员。返回匹配的人员列表（含工号、姓名、部门、岗位）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词（姓名/工号/英文名）"}
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_superior_chain",
        "description": "获取某人的完整上级汇报链，从本人到最顶层领导。需要先用 search_person 找到工号。",
        "input_schema": {
            "type": "object",
            "properties": {
                "empno": {"type": "string", "description": "员工工号"}
            },
            "required": ["empno"],
        },
    },
    {
        "name": "get_subordinates",
        "description": "获取某人的直属下属（可指定层级深度）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "empno": {"type": "string", "description": "员工工号"},
                "depth": {"type": "integer", "description": "下属层级深度，默认1", "default": 1},
            },
            "required": ["empno"],
        },
    },
    {
        "name": "find_path",
        "description": "查找两人之间的最短汇报路径。",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_empno": {"type": "string", "description": "起点员工工号"},
                "to_empno": {"type": "string", "description": "终点员工工号"},
            },
            "required": ["from_empno", "to_empno"],
        },
    },
    {
        "name": "find_common_superior",
        "description": "查找两人的最低共同上级。",
        "input_schema": {
            "type": "object",
            "properties": {
                "empno_a": {"type": "string", "description": "第一人工号"},
                "empno_b": {"type": "string", "description": "第二人工号"},
            },
            "required": ["empno_a", "empno_b"],
        },
    },
    {
        "name": "get_dept_members",
        "description": "获取某个部门的所有在职成员列表。",
        "input_schema": {
            "type": "object",
            "properties": {
                "deptname": {"type": "string", "description": "部门名称（精确匹配）"}
            },
            "required": ["deptname"],
        },
    },
    {
        "name": "get_dept_members_by_no",
        "description": "根据部门编号获取该部门所有在职成员。传入任意一种部门编号（deptno 或 deptnosap 均可），系统会自动匹配。",
        "input_schema": {
            "type": "object",
            "properties": {
                "deptno": {"type": "string", "description": "部门编号（deptno 或 deptnosap 均可）"}
            },
            "required": ["deptno"],
        },
    },
    {
        "name": "get_stats",
        "description": "获取组织图谱统计信息：总人数、部门数、最大层级深度。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _execute_tool(G: nx.MultiDiGraph, tool_name: str, tool_input: dict) -> str:
    """执行图查询工具，返回 JSON 结果字符串。"""
    print(f"[nl_query] tool_call: {tool_name}({tool_input})", file=sys.stderr)
    t0 = time.time()

    if tool_name == "search_person":
        result = graph_query.search_person(G, tool_input["keyword"])
    elif tool_name == "get_superior_chain":
        result = graph_query.get_superior_chain(G, tool_input["empno"])
    elif tool_name == "get_subordinates":
        result = graph_query.get_subordinates(G, tool_input["empno"], tool_input.get("depth", 1))
    elif tool_name == "find_path":
        result = graph_query.find_path(G, tool_input["from_empno"], tool_input["to_empno"])
    elif tool_name == "find_common_superior":
        result = graph_query.find_common_superior(G, tool_input["empno_a"], tool_input["empno_b"])
    elif tool_name == "get_dept_members":
        result = graph_query.get_dept_members(G, tool_input["deptname"])
    elif tool_name == "get_dept_members_by_no":
        deptno, deptnosap = dept_manager.resolve_dept_codes(tool_input["deptno"])
        print(f"[nl_query]   resolve_dept_codes({tool_input['deptno']!r}) -> deptno={deptno!r}, deptnosap={deptnosap!r}", file=sys.stderr)
        result = graph_query.get_dept_members_by_no(G, deptno, deptnosap)
    elif tool_name == "get_stats":
        result = graph_query.get_stats(G)
    else:
        result = {"error": f"未知工具: {tool_name}"}

    elapsed = (time.time() - t0) * 1000
    count = len(result) if isinstance(result, list) else None
    count_info = f", count={count}" if count is not None else ""
    print(f"[nl_query] tool_done: {tool_name} ({elapsed:.1f}ms{count_info})", file=sys.stderr)
    return json.dumps(result, ensure_ascii=False)


def ask(question: str, G: nx.MultiDiGraph) -> str:
    """
    自然语言图谱问答。

    流程：用户问题 -> Claude 选择工具 -> 执行图查询 -> Claude 生成答案。
    支持多轮工具调用（Claude 可能需要先搜索再查链）。
    """
    print(f"[nl_query] === ask start === question={question!r}", file=sys.stderr)
    t_start = time.time()

    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
        base_url=os.environ.get("ANTHROPIC_BASE_URL"),
    )

    messages = [{"role": "user", "content": question}]
    system_prompt = (
        "你是组织架构助手，通过查询公司人员关系图来回答问题。"
        "图中包含员工的直属上级、第二上级、部门负责人、体系负责人等关系。"
        "如果需要查找某人的工号，先用 search_person 搜索。"
        "回答要简洁明了，使用中文。"
    )

    tool_chain = []

    # 最多 5 轮工具调用
    for round_i in range(5):
        print(f"[nl_query] round {round_i + 1}: calling LLM...", file=sys.stderr)
        t_llm = time.time()
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )
        llm_ms = (time.time() - t_llm) * 1000
        print(f"[nl_query] round {round_i + 1}: LLM responded ({llm_ms:.0f}ms), stop_reason={response.stop_reason}", file=sys.stderr)

        if response.stop_reason == "end_turn":
            # Claude 给出了最终答案
            total_ms = (time.time() - t_start) * 1000
            chain_str = " -> ".join(tool_chain) if tool_chain else "(no tools)"
            print(f"[nl_query] === ask done === chain: {chain_str} | total: {total_ms:.0f}ms", file=sys.stderr)
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            # 执行工具调用
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_chain.append(f"{block.name}({json.dumps(tool_input_summary(block.input), ensure_ascii=False)})")
                    result = _execute_tool(G, block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    total_ms = (time.time() - t_start) * 1000
    chain_str = " -> ".join(tool_chain) if tool_chain else "(no tools)"
    print(f"[nl_query] === ask failed === chain: {chain_str} | total: {total_ms:.0f}ms", file=sys.stderr)
    return "抱歉，无法回答该问题。请尝试更具体的描述，例如：'张三的直属上级是谁'、'技术部有多少人'。"


def tool_input_summary(input_dict: dict) -> dict:
    """缩略工具入参，避免日志过长。"""
    return {k: v for k, v in input_dict.items()}
