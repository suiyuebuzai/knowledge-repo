# knowledge-server/tests/test_builder.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.builder import build_graph, EDGE_FIELDS


def _make_records():
    """构造测试用人员数据。"""
    return [
        {"empno": "001", "empname": "CEO", "deptname": "总裁办", "divname": "集团",
         "engroup": "Group", "jobname": "CEO", "enname": "CEO", "email": "ceo@co.com",
         "directsuperior": None, "secondsuperior": None, "foreman": None, "f045": None, "f046": None},
        {"empno": "002", "empname": "VP张", "deptname": "技术部", "divname": "技术体系",
         "engroup": "Tech", "jobname": "VP", "enname": "VP Zhang", "email": "vp@co.com",
         "directsuperior": "001", "secondsuperior": None, "foreman": None, "f045": "001", "f046": "001"},
        {"empno": "003", "empname": "经理李", "deptname": "技术部", "divname": "技术体系",
         "engroup": "Tech", "jobname": "经理", "enname": "Manager Li", "email": "li@co.com",
         "directsuperior": "002", "secondsuperior": "001", "foreman": None, "f045": "002", "f046": "001"},
        {"empno": "004", "empname": "工程师王", "deptname": "技术部", "divname": "技术体系",
         "engroup": "Tech", "jobname": "工程师", "enname": "Eng Wang", "email": "wang@co.com",
         "directsuperior": "003", "secondsuperior": "002", "foreman": None, "f045": "002", "f046": "001"},
        {"empno": "005", "empname": "财务赵", "deptname": "财务部", "divname": "职能体系",
         "engroup": "Func", "jobname": "会计", "enname": "Zhao", "email": "zhao@co.com",
         "directsuperior": "001", "secondsuperior": None, "foreman": None, "f045": "001", "f046": "001"},
    ]


def test_build_graph_node_count():
    G = build_graph(_make_records())
    assert G.number_of_nodes() == 5


def test_build_graph_node_attributes():
    G = build_graph(_make_records())
    assert G.nodes["003"]["empname"] == "经理李"
    assert G.nodes["003"]["deptname"] == "技术部"
    assert G.nodes["003"]["jobname"] == "经理"


def test_build_graph_edges():
    G = build_graph(_make_records())
    # 002 reports to 001
    assert G.has_edge("002", "001")
    edge_types_002_001 = {d["type"] for u, v, d in G.edges("002", data=True) if v == "001"}
    assert "REPORTS_TO" in edge_types_002_001


def test_build_graph_skips_missing_target():
    """如果上级工号不在图中，不应创建边。"""
    records = [
        {"empno": "099", "empname": "孤立者", "deptname": "X", "divname": "X",
         "engroup": "X", "jobname": "X", "enname": "X", "email": "",
         "directsuperior": "999", "secondsuperior": None, "foreman": None, "f045": None, "f046": None},
    ]
    G = build_graph(records)
    assert G.number_of_nodes() == 1
    assert G.number_of_edges() == 0


def test_build_graph_multiple_edge_types():
    G = build_graph(_make_records())
    # 003 has edges: directsuperior→002, secondsuperior→001, f045→002, f046→001
    edge_types = {d["type"] for u, v, k, d in G.out_edges("003", data=True, keys=True)}
    assert "REPORTS_TO" in edge_types
    assert "SECOND_REPORTS_TO" in edge_types
    assert "DEPT_HEAD" in edge_types
    assert "DIV_HEAD" in edge_types
