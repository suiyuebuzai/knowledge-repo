# knowledge-server/graph/loader.py
"""
人员数据加载与图缓存管理。

GraphManager 负责：
- 从 lakehouse API 分页拉取在职人员数据
- 本地 JSON 文件缓存（重启免拉取）
- 构建 NetworkX 图并内存缓存
- 手动刷新时重新拉取 API 并更新本地缓存
"""
import json
import time
import sys
from pathlib import Path

import networkx as nx

import config
from lakehouse import query_dataset
from graph.builder import build_graph

# 拉取字段白名单（减少数据量）
_FIELDS = [
    "empno", "empname", "enname", "loginname", "email",
    "deptno", "deptname", "bunitno", "divname", "engroup",
    "jobno", "jobname", "hrstatus",
    "directsuperior", "secondsuperior", "foreman", "f045", "f046",
]

# 本地缓存文件路径
_CACHE_FILE = Path(config.BASE_DIR) / "graph" / ".employees_cache.json"


def _save_cache(records: list[dict]) -> None:
    """将记录保存到本地 JSON 缓存。"""
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    print(f"[graph/loader] cache saved: {len(records)} records", file=sys.stderr)


def _load_cache() -> list[dict] | None:
    """从本地缓存加载记录，不存在则返回 None。"""
    if not _CACHE_FILE.exists():
        return None
    try:
        records = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        age_hours = (time.time() - _CACHE_FILE.stat().st_mtime) / 3600
        print(f"[graph/loader] cache loaded: {len(records)} records (age: {age_hours:.1f}h)", file=sys.stderr)
        return records
    except (json.JSONDecodeError, OSError) as e:
        print(f"[graph/loader] cache read failed: {e}", file=sys.stderr)
        return None


def fetch_all_employees() -> list[dict]:
    """分页拉取所有在职人员。"""
    all_records = []
    offset = 0
    limit = 10000

    while True:
        print(f"[graph/loader] fetching offset={offset}...", file=sys.stderr)
        result = query_dataset(
            tgt_svc=config.OA_DATA_SVC,
            dataset_name="it_oa_userlevels",
            filters=[("hrstatus", "EQ", "在职")],
            fields=_FIELDS,
            limit=limit,
            offset=offset,
        )
        records = result.get("records", [])
        all_records.extend(records)
        print(f"[graph/loader] got {len(records)}, total {len(all_records)}", file=sys.stderr)

        if len(records) < limit:
            break
        offset += limit

    return all_records


class GraphManager:
    """图数据管理器：本地缓存 + 内存缓存。"""

    def __init__(self):
        self._graph: nx.MultiDiGraph | None = None
        self._loaded_at: float = 0
        self._loading: bool = False

    @property
    def is_loaded(self) -> bool:
        return self._graph is not None

    @property
    def is_stale(self) -> bool:
        if self._graph is None:
            return True
        return time.time() - self._loaded_at > config.GRAPH_TTL

    def get_graph(self) -> nx.MultiDiGraph | None:
        """获取图。如果未加载则返回 None。"""
        return self._graph

    def load_from_cache(self) -> bool:
        """从本地缓存加载图。成功返回 True，无缓存返回 False。"""
        records = _load_cache()
        if records is None:
            return False
        self._graph = build_graph(records)
        self._loaded_at = time.time()
        print(
            f"[graph/loader] loaded from cache: {self._graph.number_of_nodes()} nodes, "
            f"{self._graph.number_of_edges()} edges",
            file=sys.stderr,
        )
        return True

    def refresh(self) -> nx.MultiDiGraph:
        """强制从 API 重新拉取并更新缓存。"""
        self._graph = None
        self._loading = True
        try:
            print("[graph/loader] refreshing from API...", file=sys.stderr)
            records = fetch_all_employees()
            _save_cache(records)
            self._graph = build_graph(records)
            self._loaded_at = time.time()
            print(
                f"[graph/loader] refreshed: {self._graph.number_of_nodes()} nodes, "
                f"{self._graph.number_of_edges()} edges",
                file=sys.stderr,
            )
            return self._graph
        finally:
            self._loading = False

    @property
    def cache_age_hours(self) -> float | None:
        """缓存文件年龄（小时），无缓存返回 None。"""
        if not _CACHE_FILE.exists():
            return None
        return (time.time() - _CACHE_FILE.stat().st_mtime) / 3600


# 全局单例
graph_manager = GraphManager()
