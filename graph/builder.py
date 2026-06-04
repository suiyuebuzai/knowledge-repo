# knowledge-server/graph/builder.py
"""将人员记录列表构建为 NetworkX 多边有向图。"""
import networkx as nx

EDGE_FIELDS = {
    "directsuperior": "REPORTS_TO",
    "secondsuperior": "SECOND_REPORTS_TO",
    "foreman": "FOREMAN",
    "f045": "DEPT_HEAD",
    "f046": "DIV_HEAD",
}

NODE_ATTRS = ["empname", "enname", "deptno", "deptname", "divname", "engroup", "jobname", "email"]


def build_graph(records: list[dict]) -> nx.MultiDiGraph:
    """
    将人员记录构建为多边有向图。

    节点 ID 为 empno，属性包含姓名/部门/岗位等。
    边从员工指向上级，类型由 EDGE_FIELDS 定义。
    同一对节点间可有多条不同类型的边。
    如果目标节点不在图中则跳过该边。
    """
    G = nx.MultiDiGraph()

    # Pass 1: 添加所有节点
    for r in records:
        empno = r.get("empno")
        if not empno:
            continue
        attrs = {k: r.get(k, "") for k in NODE_ATTRS}
        G.add_node(empno, **attrs)

    # Pass 2: 添加边（仅当目标存在于图中时）
    for r in records:
        empno = r.get("empno")
        if not empno:
            continue
        for field, edge_type in EDGE_FIELDS.items():
            target = r.get(field)
            if target and target in G:
                G.add_edge(empno, target, type=edge_type)

    return G
