# lakehouse/__init__.py
"""
数据湖仓 API 模块。

双形态：
- 直接 import：from lakehouse import query_dataset, get_dataset_fields
- MCP Server：python lakehouse/server.py → http://localhost:8000/sse
"""
from lakehouse.client import query_dataset, get_record, list_datasets, get_dataset_fields

__all__ = ["query_dataset", "get_record", "list_datasets", "get_dataset_fields"]
