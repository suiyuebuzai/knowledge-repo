# graph/dept_loader.py
"""
部门层级数据加载与缓存管理。

DeptManager 负责：
- 从 lakehouse API 拉取部门 + 体系数据
- 本地 JSON 文件缓存（重启免拉取）
- 构建树形结构并内存缓存
- 手动刷新时重新拉取 API 并更新缓存
"""
import json
import time
import sys
from pathlib import Path

import config
from lakehouse import query_dataset

_CACHE_FILE = Path(config.BASE_DIR) / "graph" / ".departments_cache.json"


def _fetch_departments() -> list[dict]:
    """分页拉取所有部门记录。"""
    all_records = []
    offset = 0
    limit = 10000

    while True:
        print(f"[dept_loader] fetching departments offset={offset}...", file=sys.stderr)
        result = query_dataset(
            tgt_svc=config.OA_DATA_SVC,
            dataset_name="it_oa_organization_departments",
            fields=[
                "id_casp", "deptno", "deptname", "deptnosap",
                "bunitno", "bunithead", "firstresponse",
                "isoverseas", "isoutworker",
            ],
            limit=limit,
            offset=offset,
        )
        records = result.get("records", [])
        all_records.extend(records)
        if len(records) < limit:
            break
        offset += limit

    print(f"[dept_loader] total departments: {len(all_records)}", file=sys.stderr)
    return all_records


def _fetch_divisions() -> dict[str, str]:
    """拉取体系主数据，返回 {bunitno: bunitname} 映射。"""
    print("[dept_loader] fetching divisions...", file=sys.stderr)
    result = query_dataset(
        tgt_svc=config.OA_DATA_SVC,
        dataset_name="it_oa_organization_divisions",
        fields=["bunitno", "bunitname"],
        limit=10000,
    )
    records = result.get("records", [])
    print(f"[dept_loader] total divisions: {len(records)}", file=sys.stderr)
    return {r["bunitno"]: r["bunitname"] for r in records if r.get("bunitno") and r.get("bunitname")}


def _build_tree(records: list[dict], division_names: dict[str, str]) -> dict:
    """将扁平部门列表 + 体系名称映射转为树形结构。"""
    dept_map = {r["deptno"]: r for r in records if r.get("deptno")}
    all_deptnos = set(dept_map.keys())

    children_map: dict[str, list[dict]] = {}
    for r in records:
        bunitno = r.get("bunitno")
        if bunitno:
            children_map.setdefault(bunitno, []).append(r)

    top_bunitnos = set(children_map.keys()) - all_deptnos

    def make_node(record: dict) -> dict:
        deptno = record["deptno"]
        node = {
            "id": deptno,
            "name": record.get("deptname") or deptno,
            "deptnosap": record.get("deptnosap"),
            "bunithead": record.get("bunithead"),
            "firstresponse": record.get("firstresponse"),
            "isoverseas": record.get("isoverseas"),
            "isoutworker": record.get("isoutworker"),
        }
        sub_records = [
            r for r in children_map.get(deptno, [])
            if r["deptno"] != deptno
        ]
        if sub_records:
            node["children"] = [make_node(r) for r in sorted(sub_records, key=lambda x: x.get("deptname", ""))]
        return node

    top_nodes = []
    for bunitno in sorted(top_bunitnos):
        children_records = children_map.get(bunitno, [])
        child_nodes = [make_node(r) for r in sorted(children_records, key=lambda x: x.get("deptname", ""))]
        top_nodes.append({
            "id": bunitno,
            "name": division_names.get(bunitno, bunitno),
            "type": "division",
            "children": child_nodes,
        })

    return {
        "id": "root",
        "name": "远景组织",
        "type": "root",
        "children": top_nodes,
    }


class DeptManager:
    """部门层级数据管理器：本地缓存 + 内存缓存。"""

    def __init__(self):
        self._tree: dict | None = None
        self._loaded_at: float = 0

    @property
    def is_loaded(self) -> bool:
        return self._tree is not None

    def get_tree(self) -> dict | None:
        return self._tree

    def load_from_cache(self) -> bool:
        """从本地 JSON 缓存加载。成功返回 True。"""
        if not _CACHE_FILE.exists():
            return False
        try:
            self._tree = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            self._loaded_at = time.time()
            age_hours = (time.time() - _CACHE_FILE.stat().st_mtime) / 3600
            n_div = len(self._tree.get("children", []))
            print(f"[dept_loader] cache loaded: {n_div} divisions (age: {age_hours:.1f}h)", file=sys.stderr)
            return True
        except (json.JSONDecodeError, OSError) as e:
            print(f"[dept_loader] cache read failed: {e}", file=sys.stderr)
            return False

    def refresh(self) -> dict:
        """从 API 重新拉取部门 + 体系数据，更新缓存。"""
        print("[dept_loader] refreshing from API...", file=sys.stderr)
        records = _fetch_departments()
        division_names = _fetch_divisions()
        self._tree = _build_tree(records, division_names)
        self._loaded_at = time.time()

        # 保存缓存
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(self._tree, ensure_ascii=False), encoding="utf-8")

        n_div = len(self._tree.get("children", []))
        n_dept = sum(len(n.get("children", [])) for n in self._tree["children"])
        print(f"[dept_loader] refreshed: {n_div} divisions, {n_dept} departments", file=sys.stderr)
        return self._tree

    def resolve_dept_codes(self, code: str) -> tuple[str, str]:
        """根据任意一种部门编号，从部门树中找到 deptno 和 deptnosap。"""
        if not self._tree:
            return code, ""

        def _search(node: dict) -> tuple[str, str] | None:
            if node.get("id") == code or node.get("deptnosap") == code:
                return node.get("id", ""), node.get("deptnosap", "")
            for child in node.get("children", []):
                found = _search(child)
                if found:
                    return found
            return None

        result = _search(self._tree)
        return result if result else (code, "")

    @property
    def cache_age_hours(self) -> float | None:
        if not _CACHE_FILE.exists():
            return None
        return (time.time() - _CACHE_FILE.stat().st_mtime) / 3600


# 全局单例
dept_manager = DeptManager()
