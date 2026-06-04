# knowledge-server/graph/query.py
"""图查询函数：搜索、上下级链、路径分析、统计。"""
import networkx as nx


def _node_to_dict(G: nx.MultiDiGraph, empno: str) -> dict:
    """将节点转为字典（含 empno）。"""
    attrs = dict(G.nodes[empno])
    attrs["empno"] = empno
    return attrs


def search_person(G: nx.MultiDiGraph, keyword: str) -> list[dict]:
    """模糊搜索人员（匹配工号、姓名、英文名）。"""
    keyword_lower = keyword.lower()
    results = []
    for empno, attrs in G.nodes(data=True):
        if (keyword_lower in empno.lower()
                or keyword_lower in (attrs.get("empname") or "").lower()
                or keyword_lower in (attrs.get("enname") or "").lower()):
            results.append({"empno": empno, **attrs})
    return results[:20]


def get_superior_chain(G: nx.MultiDiGraph, empno: str) -> list[dict]:
    """沿 REPORTS_TO 边向上追溯完整上级链。返回从自身到最顶层的列表。"""
    if empno not in G:
        return []
    chain = [_node_to_dict(G, empno)]
    visited = {empno}
    current = empno
    while True:
        superior = None
        for _, target, data in G.out_edges(current, data=True):
            if data.get("type") == "REPORTS_TO":
                superior = target
                break
        if superior is None or superior in visited:
            break
        visited.add(superior)
        chain.append(_node_to_dict(G, superior))
        current = superior
    return chain


def get_subordinates(G: nx.MultiDiGraph, empno: str, depth: int = 1) -> list[dict]:
    """获取 N 层直属下属（通过反向 REPORTS_TO 边）。"""
    if empno not in G:
        return []
    result = []
    current_level = {empno}
    visited = {empno}
    for _ in range(depth):
        next_level = set()
        for node in current_level:
            for source, _, data in G.in_edges(node, data=True):
                if data.get("type") == "REPORTS_TO" and source not in visited:
                    visited.add(source)
                    next_level.add(source)
                    result.append(_node_to_dict(G, source))
        current_level = next_level
        if not current_level:
            break
    return result


def get_neighbors(G: nx.MultiDiGraph, empno: str, depth: int = 2, max_nodes: int = 80) -> dict:
    """获取某人 N 层关系网络，返回 vis.js 格式 {center, nodes, edges}。

    max_nodes 限制返回的最大节点数，防止大图卡死前端。
    """
    if empno not in G:
        return {"center": empno, "nodes": [], "edges": []}

    # BFS 收集 N 层内的所有节点（不区分边方向），受 max_nodes 限制
    visited = {empno}
    current_level = {empno}
    for _ in range(depth):
        next_level = set()
        for node in current_level:
            for neighbor in set(G.successors(node)) | set(G.predecessors(node)):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_level.add(neighbor)
                    if len(visited) >= max_nodes:
                        break
            if len(visited) >= max_nodes:
                break
        current_level = next_level
        if not current_level or len(visited) >= max_nodes:
            break

    # 构造 vis.js 格式
    nodes = []
    for nid in visited:
        attrs = G.nodes[nid]
        sub_count = sum(1 for _, _, d in G.in_edges(nid, data=True) if d.get("type") == "REPORTS_TO")
        nodes.append({
            "id": nid,
            "label": attrs.get("empname", nid),
            "title": f"{attrs.get('deptname', '')} | {attrs.get('jobname', '')}",
            "group": attrs.get("divname", ""),
            "size": 10 + min(sub_count * 3, 30),
        })

    edges = []
    edge_labels = {
        "REPORTS_TO": "直属上级",
        "SECOND_REPORTS_TO": "第二上级",
        "FOREMAN": "班组长",
        "DEPT_HEAD": "部门负责人",
        "DIV_HEAD": "体系负责人",
    }
    # 优先级：同一对节点间只保留最重要的边，避免重叠
    edge_priority = {"REPORTS_TO": 0, "SECOND_REPORTS_TO": 1, "FOREMAN": 2, "DEPT_HEAD": 3, "DIV_HEAD": 4}
    seen_edges: dict[tuple[str, str], int] = {}
    edge_candidates = []
    for u, v, data in G.edges(data=True):
        if u in visited and v in visited:
            etype = data.get("type", "")
            priority = edge_priority.get(etype, 99)
            key = (u, v)
            if key not in seen_edges or priority < seen_edges[key]:
                seen_edges[key] = priority
                edge_candidates.append((u, v, etype, priority))

    # 过滤只保留每对节点优先级最高的边
    for u, v, etype, priority in edge_candidates:
        if seen_edges.get((u, v)) == priority:
            edges.append({
                "from": u,
                "to": v,
                "label": edge_labels.get(etype, ""),
                "arrows": "to",
            })

    return {"center": empno, "nodes": nodes, "edges": edges}


def find_path(G: nx.MultiDiGraph, from_empno: str, to_empno: str) -> list[dict]:
    """找两人之间的最短路径（忽略边方向）。不连通时返回空列表。"""
    if from_empno not in G or to_empno not in G:
        return []
    try:
        path = nx.shortest_path(G.to_undirected(), from_empno, to_empno)
        return [_node_to_dict(G, nid) for nid in path]
    except nx.NetworkXNoPath:
        return []


def find_common_superior(G: nx.MultiDiGraph, empno_a: str, empno_b: str) -> dict | None:
    """找两人的最低共同上级（沿 REPORTS_TO 向上找交集）。"""
    if empno_a not in G or empno_b not in G:
        return None

    def _get_chain(empno: str) -> list[str]:
        chain = [empno]
        current = empno
        visited = {empno}
        while True:
            superior = None
            for _, target, data in G.out_edges(current, data=True):
                if data.get("type") == "REPORTS_TO":
                    superior = target
                    break
            if superior is None or superior in visited:
                break
            visited.add(superior)
            chain.append(superior)
            current = superior
        return chain

    chain_a = _get_chain(empno_a)
    chain_b_set = set(_get_chain(empno_b))

    # 从 A 链底部往上找，第一个同时在 B 链中且不是 A/B 本身的
    for node in chain_a:
        if node in chain_b_set and node != empno_a and node != empno_b:
            return _node_to_dict(G, node)

    # 如果 A 本身在 B 的链中（A 是 B 的上级）
    if empno_a in chain_b_set and empno_a != empno_b:
        return _node_to_dict(G, empno_a)
    # 如果 B 本身在 A 的链中（B 是 A 的上级）
    if empno_b in set(chain_a) and empno_b != empno_a:
        return _node_to_dict(G, empno_b)

    return None


def get_dept_members(G: nx.MultiDiGraph, deptname: str) -> list[dict]:
    """获取某部门所有成员（按部门名称）。"""
    return [
        {"empno": empno, **attrs}
        for empno, attrs in G.nodes(data=True)
        if attrs.get("deptname") == deptname
    ]


def get_dept_members_by_no(G: nx.MultiDiGraph, deptno: str, deptnosap: str = "") -> list[dict]:
    """获取某部门所有成员（按部门编号，同时匹配 deptno 和 deptnosap）。"""
    codes = {deptno}
    if deptnosap:
        codes.add(deptnosap)
    return [
        {"empno": empno, **attrs}
        for empno, attrs in G.nodes(data=True)
        if attrs.get("deptno") in codes
    ]


def get_stats(G: nx.MultiDiGraph) -> dict:
    """统计：总人数、部门数、最大汇报层级深度。"""
    departments = set()
    for _, attrs in G.nodes(data=True):
        dept = attrs.get("deptname", "")
        if dept:
            departments.add(dept)

    # 计算最大深度：找没有 REPORTS_TO 出边的节点（顶层），BFS 计算深度
    max_depth = 0
    for node in G.nodes():
        has_superior = any(d.get("type") == "REPORTS_TO" for _, _, d in G.out_edges(node, data=True))
        if not has_superior:
            depth = _calc_depth(G, node)
            max_depth = max(max_depth, depth)

    return {
        "total_persons": G.number_of_nodes(),
        "total_departments": len(departments),
        "total_edges": G.number_of_edges(),
        "max_depth": max_depth,
    }


def _calc_depth(G: nx.MultiDiGraph, root: str) -> int:
    """从 root 向下计算最大深度（通过反向 REPORTS_TO）。"""
    depth = 1
    current_level = {root}
    visited = {root}
    while current_level:
        next_level = set()
        for node in current_level:
            for source, _, data in G.in_edges(node, data=True):
                if data.get("type") == "REPORTS_TO" and source not in visited:
                    visited.add(source)
                    next_level.add(source)
        if next_level:
            depth += 1
        current_level = next_level
    return depth
