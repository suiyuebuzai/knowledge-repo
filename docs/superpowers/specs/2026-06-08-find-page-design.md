# 找文档页面设计文档

**日期：** 2026-06-08  
**状态：** 已批准，待实现  
**定位：** 在 Web App 中新增「找文档」页面，让用户通过浏览器扫描本机任意目录，筛选文件后一键索引进知识库。

---

## 背景

`ingest.py` 已实现 `find_documents()` 函数（`find` 子命令），支持递归扫描目录、扩展名过滤、文件名模糊匹配。现有 Web App 缺少对应的前端入口——用户只能通过「传文件」手动上传，无法浏览本机目录。本页面补全这一缺口。

---

## 改动范围

| 文件 | 改动 |
|------|------|
| `web_app.py` | 新增 3 个路由：`GET /find`、`GET /find/api/scan`、`POST /find/api/index` |
| `templates/find.html` | 新建，找文档页面 |
| `templates/base.html` | 侧边栏「知识库」分组新增「找文档」入口 |

---

## 后端 API

### GET /find
返回 `find.html` 页面，无额外参数。

### GET /find/api/scan

**参数：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `dir` | string | `config.DOCS_DIR` | 要扫描的根目录绝对路径 |
| `query` | string | `""` | 文件名模糊过滤（子串或 `*/?` 通配符） |
| `ext` | string | `".pdf,.docx,.txt,.md"` | 逗号分隔的扩展名 |
| `recursive` | bool | `true` | 是否递归子目录 |

**成功响应（200）：**
```json
{
  "total": 15,
  "files": [
    {
      "name": "合同模板.pdf",
      "ext": ".PDF",
      "size": "123.4 KB",
      "mtime": "2026-06-01",
      "rel_path": "subdir/合同模板.pdf",
      "abs_path": "C:/1AI/.../合同模板.pdf"
    }
  ]
}
```

**错误响应（200，error 字段）：**
```json
{ "error": "目录不存在：C:/不存在的路径" }
```

实现：直接调用 `ingest.find_documents()`，对返回的 `Path` 列表做元数据序列化。

### POST /find/api/index

**请求 body（JSON）：**
```json
{ "files": ["C:/1AI/.../合同模板.pdf", "C:/1AI/.../报告.docx"] }
```

**响应：** `text/event-stream`（SSE）

```
data: {"file": "合同模板.pdf", "status": "indexing"}

data: {"file": "合同模板.pdf", "status": "done", "chunks": 12}

data: {"file": "报告.docx", "status": "error", "error": "解析失败: ..."}

event: done
data: {"total": 2, "success": 1, "failed": 1}
```

实现：对每个文件依次调用 `chunker.load_and_chunk()` → `embedder.embed()` → `store.upsert()`，每步完成后 yield SSE 消息。

---

## 前端页面（find.html）

### 布局

```
┌──────────────────────────────────────────────────────┐
│ 找文档                                                │
├──────────────────────────────────────────────────────┤
│ 目录路径: [__________________________]  [扫 描]       │
│ 文件名关键词: [___________]  ☑ 递归子目录             │
│ 扩展名: ☑ PDF  ☑ DOCX  ☑ TXT  ☑ MD                 │
├──────────────────────────────────────────────────────┤
│ 找到 15 个文件   [全选] [取消全选]   [索引选中 (3) ▶] │
│ ──────────────────────────────────────────────────── │
│ ☑ # 文件名         类型  大小    修改时间   相对路径  │
│ ☑ 1 合同模板.pdf  .PDF  123KB  2026-06-01  sub/...  │
│ ☐ 2 报告.docx    .DOCX  45KB  2026-05-20  ...      │
├──────────────────────────────────────────────────────┤
│ 正在索引...                                           │
│ ✓ 合同模板.pdf — 12 个片段                            │
│ ✓ 报告.docx   — 8 个片段                              │
│ ✗ 损坏文件.pdf — 解析失败: ...                         │
│ 完成：2 成功，1 失败                                   │
└──────────────────────────────────────────────────────┘
```

### 交互细节

- 目录路径默认值为 `config.DOCS_DIR`（由模板注入）
- 扫描按钮点击时禁用，结果返回后恢复
- 「索引选中 (N)」按钮上的数字随 checkbox 勾选实时更新；N=0 时按钮禁用
- 进度区域默认隐藏，点击索引后显示
- 索引完成后进度区域追加「完成：X 成功，Y 失败」一行

### 导航

`base.html` 侧边栏知识库分组：

```
知识库
  · 问知识
  · 搜文档
  · 传文件
  · 找文档   ← 新增（active = "find"）
```

---

## 数据流

```
用户输入目录 + 过滤条件
    → JS fetch GET /find/api/scan
    → web_app.py: ingest.find_documents() → 序列化元数据
    → JSON 响应 → 前端动态渲染表格

用户勾选文件 → 点「索引选中」
    → JS fetch POST /find/api/index {files:[...]}
    → web_app.py 遍历文件:
        chunker.load_and_chunk → embedder.embed → store.upsert
        → SSE: {file, status, chunks}
    → event: done → 前端显示最终统计
```

---

## 不做的事情

- 不做目录树浏览（用输入框，不做文件系统 UI）
- 不做已索引状态标记（不查 ChromaDB 判断每个文件是否已索引）
- 不做文件预览
- 不做路径安全校验（本地工具，信任用户输入）
