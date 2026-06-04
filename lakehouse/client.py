# lakehouse/client.py
"""
Envision 数据湖仓 REST API 客户端。

提供 4 个核心函数：
- query_dataset   按条件查询数据集记录
- get_record      按唯一 ID 取单条记录
- list_datasets   列出当前应用下所有数据集
- get_dataset_fields  查询数据集字段结构

既可直接 import 调用（from lakehouse import query_dataset），
也可通过 lakehouse/server.py 以 MCP SSE 方式暴露给 AI Agent。
"""
from __future__ import annotations

from typing import Any

import httpx

import config
from lakehouse.auth import token_manager


# ── 内部工具 ──────────────────────────────────────────────────────

def _build_url(tgt_svc: str, path_suffix: str) -> str:
    """tgt_svc 转 URL 路径段：'it-lightning-datalakeprivate' → 'it/lightning/datalakeprivate'"""
    svc_path = tgt_svc.replace("-", "/")
    return f"{config.ENVISION_BASE_URL}/apis/{svc_path}/{path_suffix}"


def _headers(tgt_svc: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-ENP-AUTH": token_manager.get_token(tgt_svc),
    }


def _parse_records(data: list[dict]) -> list[dict]:
    """将 JSON:API data 列表转为扁平字典列表。"""
    result = []
    for item in data:
        record = {"_id": item.get("id")}
        record.update(item.get("attributes", {}))
        result.append(record)
    return result


# ── 公开 API ──────────────────────────────────────────────────────

def query_dataset(
    tgt_svc: str,
    dataset_name: str,
    filters: list[tuple[str, str, str]] | None = None,
    fields: list[str] | None = None,
    sort: list[str] | None = None,
    limit: int = 10000,
    offset: int = 0,
) -> dict[str, Any]:
    """
    按条件查询数据集，返回记录列表和分页信息。

    参数:
        tgt_svc       目标服务名，如 "it-oa-datalakeinternal"
        dataset_name  数据集名称
        filters       过滤条件 [(字段, 操作符, 值), ...]，操作符: EQ/NEQ/GT/LT/GE/LE/LIKE
        fields        返回字段列表，None 则全部
        sort          排序规则，"-" 前缀降序
        limit         每页记录数，最大 10000
        offset        偏移量

    返回:
        {"records": [...], "total": int, "limit": int, "offset": int}
    """
    url = _build_url(tgt_svc, dataset_name)

    params: dict[str, Any] = {
        "page[limit]": limit,
        "page[offset]": offset,
    }
    if filters:
        for field, operator, value in filters:
            params[f"filter[{field}][{operator}]"] = value
    if fields:
        params["fields"] = ",".join(fields)
    if sort:
        params["sort"] = ",".join(sort)

    resp = httpx.get(url, headers=_headers(tgt_svc), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    return {
        "records": _parse_records(data.get("data", [])),
        "total": data.get("meta", {}).get("total_resource_count", 0),
        "limit": limit,
        "offset": offset,
    }


def get_record(tgt_svc: str, dataset_name: str, caspian_id: str) -> dict[str, Any] | None:
    """
    按数据湖编号（caspian_id）查询单条记录。

    返回单条记录字典，或 None（不存在时）。
    """
    url = _build_url(tgt_svc, dataset_name)
    resp = httpx.get(
        url,
        headers=_headers(tgt_svc),
        params={"filter[caspian_id][EQ]": caspian_id},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        return None
    return _parse_records(data)[0]


def list_datasets() -> list[dict[str, Any]]:
    """
    列出当前 app_id 下所有已发布的数据集。

    使用 Catalog API（tgt_svc = DATALAKE_TGT_SVC）。

    返回数据集列表，每项含 name, display_name, native_name, enable_ai_agent_access。
    """
    tgt_svc = config.DATALAKE_TGT_SVC
    catalog_path = tgt_svc.replace("-", "/")
    url = f"{config.ENVISION_BASE_URL}/apis/{catalog_path}/datasets/actions/fetch-by-appid"
    resp = httpx.get(
        url,
        headers=_headers(tgt_svc),
        params={"appId": config.ENVISION_APP_ID},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_dataset_fields(dataset_name: str) -> list[dict[str, Any]]:
    """
    查询数据集的字段详情。

    使用 Catalog API（tgt_svc = DATALAKE_TGT_SVC）。

    返回字段列表，每项含:
        name, field_type, precision, remark, is_primary, sample_value
    """
    tgt_svc = config.DATALAKE_TGT_SVC
    catalog_path = tgt_svc.replace("-", "/")
    url = f"{config.ENVISION_BASE_URL}/apis/{catalog_path}/datafields/actions/query-by-dataset-name/{dataset_name}"
    resp = httpx.get(url, headers=_headers(tgt_svc), timeout=30)
    resp.raise_for_status()
    return resp.json()
