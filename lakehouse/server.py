# lakehouse/server.py
"""
Lakehouse MCP Server

将数据湖仓查询能力通过 MCP 协议暴露给 AI Agent。

启动方式（SSE 模式）：
    cd knowledge-server
    C:/1AI/.pvenv/Scripts/python.exe lakehouse/server.py
    → http://localhost:8000/sse

工具列表：
    query_dataset      按条件查询数据集
    get_record         按唯一 ID 获取单条记录
    list_datasets      列出可用数据集
    describe_dataset   查看数据集字段结构
"""
import json
import os
import sys
from pathlib import Path

# 确保能 import 同级和上级模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP

from lakehouse.client import (
    query_dataset as _query_dataset,
    get_record as _get_record,
    list_datasets as _list_datasets,
    get_dataset_fields as _get_dataset_fields,
)

_port = int(os.environ.get("LAKEHOUSE_SERVER_PORT", "8000"))
mcp = FastMCP("lakehouse", port=_port)


@mcp.tool()
def query_dataset(
    tgt_svc: str,
    dataset_name: str,
    filters: str = "[]",
    fields: str = "",
    sort: str = "",
    limit: int = 100,
    offset: int = 0,
) -> str:
    """
    查询数据湖仓中的数据集记录。

    Args:
        tgt_svc:      目标服务名，例如 it-lightning-datalakeprivate / it-oa-datalakeinternal
        dataset_name: 数据集名称，例如 it_lightning_wbs_master_data
        filters:      过滤条件，JSON 格式二维数组 [["字段","操作符","值"], ...]
                      操作符: EQ/NEQ/GT/LT/GE/LE/LIKE。不过滤传 "[]"
        fields:       返回字段，逗号分隔。不指定则全部
        sort:         排序规则，逗号分隔，"-"前缀降序
        limit:        每页记录数，默认100，最大10000
        offset:       偏移量，需为 limit 整数倍
    """
    try:
        filter_list = json.loads(filters)
    except json.JSONDecodeError:
        return json.dumps({"error": f"filters 格式错误，需为 JSON 数组: {filters}"}, ensure_ascii=False)

    result = _query_dataset(
        tgt_svc=tgt_svc,
        dataset_name=dataset_name,
        filters=[(f[0], f[1], f[2]) for f in filter_list] if filter_list else None,
        fields=fields.split(",") if fields else None,
        sort=sort.split(",") if sort else None,
        limit=limit,
        offset=offset,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def get_record(tgt_svc: str, dataset_name: str, caspian_id: str) -> str:
    """
    按数据湖编号获取单条记录。

    Args:
        tgt_svc:      目标服务名
        dataset_name: 数据集名称
        caspian_id:   数据湖编号（caspian_id 字段值，数据集内唯一）
    """
    record = _get_record(tgt_svc, dataset_name, caspian_id)
    return json.dumps(record, ensure_ascii=False, default=str)


@mcp.tool()
def list_datasets() -> str:
    """列出当前应用下所有已发布的数据集。"""
    datasets = _list_datasets()
    return json.dumps({"datasets": datasets, "total": len(datasets)}, ensure_ascii=False, default=str)


@mcp.tool()
def describe_dataset(dataset_name: str) -> str:
    """
    查看数据集的字段结构（字段名、类型、说明、样例值）。

    Args:
        dataset_name: 数据集名称，例如 it_oa_userlevels
    """
    raw_fields = _get_dataset_fields(dataset_name)
    fields = [
        {
            "name": f.get("name"),
            "field_type": f.get("field_type"),
            "precision": f.get("precision"),
            "remark": f.get("remark"),
            "is_primary": f.get("is_primary"),
            "sample_value": f.get("sample_value"),
        }
        for f in raw_fields
    ]
    return json.dumps({
        "dataset_name": dataset_name,
        "field_count": len(fields),
        "fields": fields,
    }, ensure_ascii=False, default=str)


if __name__ == "__main__":
    mcp.run(transport="sse")
