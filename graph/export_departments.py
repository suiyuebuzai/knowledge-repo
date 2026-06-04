# graph/export_departments.py
"""
从 prod 环境导出 it_oa_organization_departments 数据，生成静态 JSON 文件。

用法：
    C:/1AI/.pvenv/Scripts/python.exe graph/export_departments.py [--env prod]

输出：
    static/data/departments.json  — 树形结构，供前端 D3 可视化使用
"""
import sys
import json
import argparse
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 加载指定环境
parser = argparse.ArgumentParser()
parser.add_argument("--env", default="prod", help="环境: prod / uat")
args = parser.parse_args()

# 替换 config 中的 env 文件加载
import os
from dotenv import load_dotenv

env_file = ROOT / f".env.{args.env}"
if not env_file.exists():
    print(f"[ERROR] 环境文件不存在: {env_file}", file=sys.stderr)
    sys.exit(1)
load_dotenv(env_file, override=True)
print(f"[export] 使用环境: {args.env} ({env_file})", file=sys.stderr)

import config  # noqa: E402 — config 读取已加载的环境变量
from lakehouse import query_dataset  # noqa: E402


def fetch_all_departments() -> list[dict]:
    """分页拉取所有部门记录。"""
    all_records = []
    offset = 0
    limit = 10000

    while True:
        print(f"[export] fetching departments offset={offset}...", file=sys.stderr)
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
        print(f"[export] got {len(records)}, total so far: {len(all_records)}", file=sys.stderr)

        if len(records) < limit:
            break
        offset += limit

    return all_records


def fetch_all_divisions() -> dict[str, str]:
    """拉取体系主数据 it_oa_organization_divisions，返回 {bunitno: bunitname} 映射。"""
    print("[export] fetching divisions...", file=sys.stderr)
    result = query_dataset(
        tgt_svc=config.OA_DATA_SVC,
        dataset_name="it_oa_organization_divisions",
        fields=["bunitno", "bunitname"],
        limit=10000,
    )
    records = result.get("records", [])
    print(f"[export] got {len(records)} divisions", file=sys.stderr)
    return {r["bunitno"]: r["bunitname"] for r in records if r.get("bunitno") and r.get("bunitname")}


def build_tree(records: list[dict], division_names: dict[str, str]) -> dict:
    """
    将扁平部门列表转为树形结构。

    参数:
        records         部门记录列表
        division_names  体系编号→体系名称映射（来自 it_oa_organization_divisions）

    层级关系：bunitno → deptno
    - bunitno 不在任何 deptno 中的，视为顶级体系节点
    - deptno == bunitno 的，视为自引用的中间层
    """
    # 索引：deptno → record
    dept_map = {r["deptno"]: r for r in records if r.get("deptno")}
    all_deptnos = set(dept_map.keys())

    # 按 bunitno 分组
    children_map: dict[str, list[dict]] = {}
    for r in records:
        bunitno = r.get("bunitno")
        if bunitno:
            children_map.setdefault(bunitno, []).append(r)

    # 识别顶级体系（bunitno 不在 deptno 中）
    top_bunitnos = set(children_map.keys()) - all_deptnos

    def make_node(record: dict) -> dict:
        """构造单个节点。"""
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
        # 查找该节点的子节点（排除自引用）
        sub_records = [
            r for r in children_map.get(deptno, [])
            if r["deptno"] != deptno
        ]
        if sub_records:
            node["children"] = [make_node(r) for r in sorted(sub_records, key=lambda x: x.get("deptname", ""))]
        return node

    # 构造顶级体系节点
    top_nodes = []
    for bunitno in sorted(top_bunitnos):
        children_records = children_map.get(bunitno, [])
        child_nodes = []
        for r in sorted(children_records, key=lambda x: x.get("deptname", "")):
            child_nodes.append(make_node(r))

        # 使用 divisions 表中的真实体系名称，找不到时回退为编号
        bunit_name = division_names.get(bunitno, bunitno)

        top_node = {
            "id": bunitno,
            "name": bunit_name,
            "type": "division",
            "children": child_nodes,
        }
        top_nodes.append(top_node)

    # 根节点
    tree = {
        "id": "root",
        "name": "远景组织",
        "type": "root",
        "children": top_nodes,
    }
    return tree


def main():
    records = fetch_all_departments()
    print(f"[export] 总共获取 {len(records)} 条部门记录", file=sys.stderr)

    division_names = fetch_all_divisions()
    print(f"[export] 体系名称映射: {len(division_names)} 条", file=sys.stderr)

    tree = build_tree(records, division_names)

    # 输出目录
    out_dir = ROOT / "static" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "departments.json"

    out_file.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] 已导出: {out_file}", file=sys.stderr)
    print(f"[export] 顶级体系: {len(tree['children'])} 个", file=sys.stderr)

    total_depts = sum(len(n.get("children", [])) for n in tree["children"])
    print(f"[export] 部门节点: {total_depts} 个", file=sys.stderr)


if __name__ == "__main__":
    main()
