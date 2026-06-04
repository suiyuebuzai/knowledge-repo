# knowledge-server/tests/test_query.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from graph.builder import build_graph
from graph.query import search_person, get_superior_chain, get_subordinates, get_neighbors


@pytest.fixture
def G():
    records = [
        {"empno": "001", "empname": "CEO王", "deptname": "总裁办", "divname": "集团",
         "engroup": "Group", "jobname": "CEO", "enname": "CEO Wang", "email": "ceo@co.com",
         "directsuperior": None, "secondsuperior": None, "foreman": None, "f045": None, "f046": None},
        {"empno": "002", "empname": "VP张三", "deptname": "技术部", "divname": "技术体系",
         "engroup": "Tech", "jobname": "VP", "enname": "VP Zhang", "email": "zhang@co.com",
         "directsuperior": "001", "secondsuperior": None, "foreman": None, "f045": "001", "f046": "001"},
        {"empno": "003", "empname": "经理李四", "deptname": "技术部", "divname": "技术体系",
         "engroup": "Tech", "jobname": "经理", "enname": "Manager Li", "email": "li@co.com",
         "directsuperior": "002", "secondsuperior": "001", "foreman": None, "f045": "002", "f046": "001"},
        {"empno": "004", "empname": "工程师王五", "deptname": "技术部", "divname": "技术体系",
         "engroup": "Tech", "jobname": "工程师", "enname": "Eng Wang Wu", "email": "wangwu@co.com",
         "directsuperior": "003", "secondsuperior": "002", "foreman": None, "f045": "002", "f046": "001"},
        {"empno": "005", "empname": "财务赵六", "deptname": "财务部", "divname": "职能体系",
         "engroup": "Func", "jobname": "会计", "enname": "Zhao Liu", "email": "zhao@co.com",
         "directsuperior": "001", "secondsuperior": None, "foreman": None, "f045": "001", "f046": "001"},
    ]
    return build_graph(records)


class TestSearchPerson:
    def test_search_by_name(self, G):
        results = search_person(G, "张三")
        assert len(results) == 1
        assert results[0]["empno"] == "002"

    def test_search_by_empno(self, G):
        results = search_person(G, "004")
        assert len(results) == 1
        assert results[0]["empname"] == "工程师王五"

    def test_search_by_enname(self, G):
        results = search_person(G, "Zhao")
        assert len(results) == 1
        assert results[0]["empno"] == "005"

    def test_search_partial_match(self, G):
        results = search_person(G, "王")
        assert len(results) == 2  # CEO王 and 工程师王五

    def test_search_no_match(self, G):
        results = search_person(G, "不存在")
        assert results == []


class TestSuperiorChain:
    def test_chain_from_bottom(self, G):
        chain = get_superior_chain(G, "004")
        empnos = [p["empno"] for p in chain]
        assert empnos == ["004", "003", "002", "001"]

    def test_chain_from_top(self, G):
        chain = get_superior_chain(G, "001")
        assert len(chain) == 1
        assert chain[0]["empno"] == "001"

    def test_chain_nonexistent(self, G):
        chain = get_superior_chain(G, "999")
        assert chain == []


class TestSubordinates:
    def test_direct_subordinates(self, G):
        subs = get_subordinates(G, "001", depth=1)
        empnos = {s["empno"] for s in subs}
        assert empnos == {"002", "005"}

    def test_deep_subordinates(self, G):
        subs = get_subordinates(G, "001", depth=3)
        empnos = {s["empno"] for s in subs}
        assert empnos == {"002", "003", "004", "005"}

    def test_leaf_node_no_subordinates(self, G):
        subs = get_subordinates(G, "004", depth=1)
        assert subs == []


class TestNeighbors:
    def test_neighbors_returns_nodes_and_edges(self, G):
        result = get_neighbors(G, "003", depth=1)
        assert "nodes" in result
        assert "edges" in result
        assert "center" in result
        assert result["center"] == "003"

    def test_neighbors_includes_center(self, G):
        result = get_neighbors(G, "003", depth=1)
        node_ids = {n["id"] for n in result["nodes"]}
        assert "003" in node_ids

    def test_neighbors_depth_2(self, G):
        result = get_neighbors(G, "003", depth=2)
        node_ids = {n["id"] for n in result["nodes"]}
        # 003's neighbors at depth 2 should include 001, 002, 004
        assert "002" in node_ids
        assert "004" in node_ids


from graph.query import find_path, find_common_superior, get_dept_members, get_stats


class TestFindPath:
    def test_path_exists(self, G):
        path = find_path(G, "004", "005")
        empnos = [p["empno"] for p in path]
        assert "001" in empnos  # 必经共同上级
        assert empnos[0] == "004"
        assert empnos[-1] == "005"

    def test_path_direct(self, G):
        path = find_path(G, "003", "002")
        assert len(path) == 2
        assert path[0]["empno"] == "003"
        assert path[1]["empno"] == "002"

    def test_path_not_found(self, G):
        """不连通时返回空。"""
        G.add_node("099", empname="孤立", deptname="", divname="", engroup="", jobname="", enname="", email="")
        path = find_path(G, "004", "099")
        assert path == []


class TestCommonSuperior:
    def test_common_superior(self, G):
        result = find_common_superior(G, "004", "005")
        assert result is not None
        assert result["empno"] == "001"

    def test_common_superior_same_branch(self, G):
        result = find_common_superior(G, "003", "004")
        assert result is not None
        # 003 is 004's direct superior, so common superior is 003 itself
        assert result["empno"] in ("002", "003")

    def test_common_superior_not_found(self, G):
        G.add_node("099", empname="孤立", deptname="", divname="", engroup="", jobname="", enname="", email="")
        result = find_common_superior(G, "004", "099")
        assert result is None


class TestDeptMembers:
    def test_dept_members(self, G):
        members = get_dept_members(G, "技术部")
        empnos = {m["empno"] for m in members}
        assert empnos == {"002", "003", "004"}

    def test_dept_not_found(self, G):
        members = get_dept_members(G, "不存在的部门")
        assert members == []


class TestStats:
    def test_stats_basic(self, G):
        stats = get_stats(G)
        assert stats["total_persons"] == 5
        assert stats["total_departments"] > 0
        assert stats["max_depth"] >= 3  # CEO→VP→经理→工程师
