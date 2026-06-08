# Knowledge 项目完整设计文档

**创建时间：** 2026-05-27（MCP Server）/ 2026-06-02（Web App + 组织图谱）/ 2026-06-03（lakehouse 模块 + UI 重构 + 混合检索）/ 2026-06-08（找文档页面）  
**状态：** MCP Server ✅ / Web App ✅ / 组织图谱 ✅ / Lakehouse 模块 ✅ / 混合检索 ✅ / 找文档页面 ✅  
**定位：** 统一知识服务平台，支持 Agent Function Calling / MCP 和 Web API 两种访问形式。包含非结构化文档混合检索（向量语义 + BM25 关键词，RRF 融合）、组织关系图谱（图查询 + NL 问答）、数据湖仓查询（Lakehouse API）等知识模块。

---

## 第一部分：MCP Server 设计

---

### 1. 目标

让 AI Agent（Claude）能通过 MCP 工具检索本地非结构化文档（PDF / Word / TXT），支持：
- 语义相似度检索，返回相关文档片段
- 内嵌 RAG，直接返回问题答案

**原型范围：** 本地文件夹 → 后期扩展到内网系统（wiki / SharePoint 等）

---

### 2. 技术选型

| 模块 | 方案 | 理由 |
|------|------|------|
| 文档解析 | `pypdf` + `python-docx` + 原生读 TXT | 轻量，无重度框架依赖 |
| Embedding | `sentence-transformers` `paraphrase-multilingual-MiniLM-L12-v2` | 公司代理无 embedding 模型权限；本地免费，支持中文 |
| 向量数据库 | ChromaDB（本地持久化） | 无需部署，原型首选；后期可迁移 Milvus |
| 关键词检索 | `rank_bm25` (BM25Plus) + `jieba` 中文分词 | 与向量语义互补，提升关键词精确匹配 |
| 融合排序 | Reciprocal Rank Fusion (RRF) | 轻量无参融合，无需训练 |
| 生成（ask_document） | `claude-sonnet-4-6` via 公司代理 | 复用现有 ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL |
| MCP Server | FastMCP（复用现有模式） | 和 lakehouse-mcp-server 一致 |

---

### 3. 目录结构

```
knowledge-server/
├── config.py          ← 统一配置（RAG + BM25 + 图谱 + Lakehouse 凭证）
├── lakehouse/         ← 数据湖仓 API 模块（双形态：函数 + MCP）
│   ├── __init__.py    ← exports: query_dataset, get_dataset_fields, ...
│   ├── auth.py        ← TokenManager（按 tgt_svc 缓存 token）
│   ├── client.py      ← 核心 API 函数（4 个）
│   └── server.py      ← MCP SSE Server（独立启动，端口 8000）
├── graph/             ← 组织图谱模块
│   ├── __init__.py
│   ├── builder.py     ← 记录 → NetworkX MultiDiGraph
│   ├── loader.py      ← 分页拉取 + 本地 JSON 缓存 + GraphManager
│   ├── query.py       ← 图查询函数（9 个）
│   ├── nl_query.py    ← Claude function calling 问答（8 个工具 + 调用链日志）
│   ├── dept_loader.py ← 部门层级数据加载与缓存（DeptManager）
│   └── export_departments.py ← CLI 导出部门树到 JSON（支持 --env prod/uat）
├── server.py          ← Knowledge MCP Server（2 个工具，端口 8001）
├── web_app.py         ← FastAPI Web 应用（左右布局，统一入口）
├── ingest.py          ← 文档索引入口
├── retriever.py       ← 混合检索（向量 + BM25 → RRF 融合）
├── bm25_store.py      ← BM25 关键词索引（jieba 分词 + BM25Plus）
├── chunker.py         ← 文档解析与分块
├── embedder.py        ← sentence-transformers 封装
├── store.py           ← ChromaDB 读写封装（写入时同步 BM25 索引）
├── templates/         ← Jinja2 模板
│   ├── base.html      ← 左右布局框架（侧边菜单 + 主内容区）
│   ├── ask.html       ← 问知识（文档问答）
│   ├── search.html    ← 搜文档（语义检索）
│   ├── upload.html    ← 传文件（文档上传）
│   ├── find.html      ← 找文档（目录扫描 + 勾选索引）
│   ├── graph.html     ← 查关系（图谱可视化）
│   ├── graph_ask.html ← 问组织（图谱问答）
│   └── dept_tree.html ← 看部门（部门层级 D3 树形图）
├── static/
│   ├── style.css      ← 全局样式（左右布局 + Markdown 排版）
│   ├── marked.min.js  ← Markdown 渲染库（本地托管）
│   └── graph.js       ← vis.js 交互
├── tests/             ← 单元测试（50+ 个）
├── docs_input/        ← 待索引文档（不提交 git）
└── chroma_db/         ← 向量库（不提交 git）
```

---

### 4. 模块接口

#### config.py
```python
DOCS_DIR     = "./docs_input"
CHROMA_DIR   = "./chroma_db"
EMBED_MODEL  = "paraphrase-multilingual-MiniLM-L12-v2"
CLAUDE_MODEL = "claude-sonnet-4-6"
CHUNK_SIZE   = 500   # 每块最大字符数
CHUNK_OVERLAP = 50   # 相邻块重叠字符数
TOP_K        = 5     # 检索返回 chunk 数
WEB_PORT     = 8080  # Web 应用端口

# BM25 混合检索
BM25_WEIGHT        = 0.3   # BM25 在 RRF 中的权重（向量权重 = 0.7）
HYBRID_CANDIDATE_K = 20    # 每路候选数（融合前）
```

#### embedder.py
```python
def embed(texts: list[str]) -> list[list[float]]:
    """批量向量化，返回 float 列表"""
```

#### store.py
```python
def upsert(chunks: list[dict]) -> None:
    """写入 ChromaDB，chunk 结构: {"id", "text", "metadata": {"source", "page"}}"""

def search(query_embedding: list[float], top_k: int) -> list[dict]:
    """返回: [{"text", "source", "score"}]"""
```

#### chunker.py
```python
def load_and_chunk(file_path: str) -> list[dict]:
    """解析 .pdf / .docx / .txt，按 CHUNK_SIZE/OVERLAP 分块，返回 chunk 列表"""
```

#### bm25_store.py
```python
def add(chunks: list[dict]) -> None:
    """追加 chunks 到 BM25 语料并重建索引（store.upsert 自动调用）"""

def rebuild_from_chroma() -> None:
    """从 ChromaDB 全量同步语料（Web App 启动时调用）"""

def search(query: str, top_k: int) -> list[dict]:
    """BM25 检索，jieba 中文分词 + BM25Plus 评分，score 归一化到 [0,1]"""
```

#### retriever.py
```python
def search(query: str, top_k: int = TOP_K) -> list[dict]:
    """混合检索：向量语义 + BM25 关键词 → RRF 融合 → top-k
    BM25 索引为空时退化为纯向量检索"""
```

---

### 5. MCP 工具

#### search_documents
```
输入: query (str), top_k (int, 默认 5)
输出: JSON 字符串
  {
    "query": "...",
    "results": [
      {"text": "...", "source": "文件名.pdf", "score": 0.91},
      ...
    ]
  }
用途: 返回原始片段，让 Claude 自己综合回答
```

#### ask_document
```
输入: question (str)
输出: 字符串答案
流程: 内部调用 retriever.search → 拼 prompt → 调 Claude API → 返回答案
用途: server 内嵌 RAG，直接给出答案
```

---

### 6. 数据流

#### 索引路径（一次性触发）
```
docs_input/ 目录
  → chunker.load_and_chunk()   # 解析文档，按段落分块
  → embedder.embed()           # batch 向量化（本地推理）
  → store.upsert()             # 写入 ChromaDB + 同步 BM25 索引
```

#### 查询路径（MCP 工具调用）
```
search_documents:
  Claude → retriever.search(query)
        → 向量路: embedder.embed → store.search (top-20)
        → BM25路: bm25_store.search (top-20, jieba 分词)
        → RRF 融合 (vec_weight=0.7, bm25_weight=0.3)
        → 归一化 + top-k → 返回 chunks JSON

ask_document:
  Claude → retriever.search(question) → 拼 prompt → Claude API → 返回答案字符串
```

---

### 7. 错误处理

| 场景 | 处理方式 |
|------|------|
| 不支持的文件格式 | ingest.py 跳过并打印警告，不中断 |
| 文件解析失败 | 记录到 stderr，跳过该文件 |
| ChromaDB 为空（未索引） | 返回 `{"error": "知识库为空，请先运行 ingest.py"}` |
| Claude API 超时/失败 | ask_document 返回检索到的 chunks，附提示"生成失败，原始片段如下" |

---

### 8. 使用方式

```bash
# 1. 安装依赖
pip install sentence-transformers chromadb pypdf python-docx mcp anthropic

# 2. 将文档放入 docs_input/
cp 合同模板.pdf knowledge-server/docs_input/

# 3. 索引文档（首次或文档更新后执行）
cd knowledge-server
python ingest.py

# 4. 启动 MCP Server（SSE 模式，默认 8001 端口）
python server.py

# 5. dlake CLI 查询（后续扩展）
dlake knowledge ask "合同到期后如何续签？"
```

---

### 9. Workbuddy MCP 配置

```json
{
  "mcpServers": {
    "lakehouse": {
      "command": "C:/1AI/.pvenv/Scripts/python.exe",
      "args": ["...lakehouse-mcp-server/server.py"],
      "env": { "APP_ENV": "uat" }
    },
    "knowledge": {
      "command": "C:/1AI/.pvenv/Scripts/python.exe",
      "args": ["...knowledge-server/server.py"]
    }
  }
}
```

---

## 第二部分：Web App 设计

---

### 10. Web App 目标

让用户通过浏览器直接与本地知识库交互，无需命令行或 MCP 客户端。  
RAG 的核心价值：让 LLM 的语言能力服务于你的私有数据，同时大幅减少幻觉。

---

### 11. Web App 技术选型

| 层 | 选择 | 理由 |
|----|------|------|
| 后端框架 | FastAPI | 已有 Python 环境，支持 SSE、文件上传、Jinja2 |
| 模板引擎 | Jinja2 | FastAPI 内置支持，服务端渲染 |
| 前端 | 原生 HTML 表单 + 少量 JS（EventSource） | 无构建工具，最简单 |
| 样式 | 单文件 CSS | 轻量，不引入框架 |
| 流式输出 | SSE (Server-Sent Events) | 问答逐字输出体验好，前端用 EventSource API |

---

### 12. Web App 路由设计

| 方法 | 路径 | 功能 | 返回 |
|------|------|------|------|
| GET | `/` | 问答页面 | Jinja2 渲染 ask.html |
| GET | `/ask/stream?q=...` | 流式问答 | SSE (text/event-stream) |
| GET | `/search` | 检索页面（无参数时空白，有 q 参数时展示结果） | Jinja2 渲染 search.html |
| GET | `/upload` | 上传页面 | Jinja2 渲染 upload.html |
| POST | `/upload` | 处理文件上传 + 索引 | 重定向回 upload 页面并显示结果 |
| GET | `/find` | 找文档页面 | Jinja2 渲染 find.html |
| GET | `/find/api/scan` | 扫描目录，返回文件列表 | JSON `{total, files[]}` |
| POST | `/find/api/index` | 索引选中文件，逐文件播报进度 | SSE (text/event-stream) |

---

### 13. Web App 功能详细设计

#### 13.1 问答页 (`/`)

**页面元素：**
- 文本输入框 + 提交按钮
- 回答展示区域（Markdown 渲染，逐字填充）
- 引用来源列表（回答完成后展示）

**流程：**
1. 用户输入问题，点击"提问"
2. 前端 JS 创建 `EventSource("/ask/stream?q=...")`
3. 后端调用 retriever → 构造 RAG prompt → Claude 流式生成
4. 逐 token 通过 SSE 推送给前端，前端累积原文 → `marked.parse()` 实时渲染为 HTML
5. 最后发送来源信息

**Markdown 渲染：**
- 使用 `marked.js`（本地 `/static/marked.min.js`，避免 CDN 网络问题）
- 流式接收时每次 `onmessage` 都重新渲染整段 markdown，保证格式实时更新
- `.answer-box` CSS 包含标题、列表、代码块、引用等 markdown 元素样式
- 图谱问答页同样使用 marked.js 渲染 AI 返回结果

**SSE 协议格式：**
```
data: 根据文档

data: ，员工每年

data: 享有10天带薪年假。

event: sources
data: [{"source": "test.txt", "score": 0.89}]

event: done
data: [DONE]
```

#### 13.2 检索页 (`/search`)

**页面元素：**
- 搜索输入框 + 搜索按钮
- 结果表格：序号、来源文件、相似度分数、文档片段预览

**流程：** 纯表单 GET 提交 → 后端调用 `retriever.search(q, top_k=10)` → Jinja2 渲染结果表格

**不调用 LLM**，纯本地 embedding + 向量检索，响应快。

#### 13.3 上传页 (`/upload`)

**页面元素：**
- 文件选择（支持多文件，accept=".pdf,.docx,.txt"）
- 上传按钮
- 已索引文件列表（从 ChromaDB metadata 聚合）
- 上传结果反馈

**流程：**
1. 保存文件到 `docs_input/`
2. `chunker.load_and_chunk()` → `embedder.embed()` → `store.upsert()`
3. 重定向回页面，显示结果消息

#### 13.4 找文档页 (`/find`)

**页面元素：**
- 目录路径输入框（默认 `config.DOCS_DIR`）+ 扫描按钮
- 过滤行：文件名关键词 / 递归子目录开关 / 扩展名复选框（PDF / DOCX / TXT / MD）
- 结果工具栏：文件数统计 + 全选/取消全选 + 「索引选中 (N)」按钮
- 结果表格：序号、文件名、类型、大小、修改时间、相对路径
- 索引进度区：逐文件显示 ⏳→✓/✗，完成后汇总

**流程：**
1. 用户输入目录路径 + 过滤条件，点击「扫描」
2. 前端 fetch `GET /find/api/scan?dir=...&query=...&ext=...&recursive=...`
3. 后端调用 `ingest.find_documents()` → 序列化文件元数据（name/ext/size/mtime/rel_path/abs_path）→ 返回 JSON
4. 前端动态渲染文件表格，勾选文件后「索引选中 (N)」按钮激活
5. 点击按钮 → fetch `POST /find/api/index {files: [...]}`
6. 后端对每个文件依次执行 `chunker.load_and_chunk → embedder.embed → store.upsert`，逐文件 SSE 播报进度
7. 前端通过 ReadableStream 消费 POST SSE，实时更新每行状态，最终显示汇总

**SSE 协议格式（POST SSE，用 fetch + ReadableStream 消费）：**
```
data: {"file": "合同模板.pdf", "status": "indexing"}
data: {"file": "合同模板.pdf", "status": "done", "chunks": 12}
data: {"file": "报告.docx",   "status": "error", "error": "..."}
event: done
data: {"total": 2, "success": 1, "failed": 1}
```

**与上传页的区别：**

| | 传文件 (`/upload`) | 找文档 (`/find`) |
|---|---|---|
| 数据来源 | 用户手动上传文件 | 扫描本机任意目录 |
| 索引方式 | 上传即自动索引（无法选择） | 扫描后勾选，按需索引 |
| 进度反馈 | 页面跳转后显示结果 | SSE 实时逐文件进度 |
| 适用场景 | 单次上传少量文件 | 批量索引本地已有文档目录 |

---

### 14. Web App 错误处理

| 场景 | 处理方式 |
|------|----------|
| 知识库为空 | 问答/检索页提示"请先上传文档" |
| Claude API 调用失败 | SSE 发送 `event: error`，前端展示错误 + 原始检索片段降级 |
| 文件格式不支持 | 上传页返回错误提示，不中断其他文件处理 |
| 目录不存在 | 找文档扫描接口返回 `{"error": "目录不存在：..."}` |
| 文件解析失败（索引时） | SSE 发送 `{"status": "error", "error": "..."}` 并继续处理下一文件 |

---

### 15. Web App 启动方式

```bash
cd knowledge-server
C:/1AI/.pvenv/Scripts/python.exe web_app.py
# → http://localhost:8080
```

与 MCP Server (`server.py`) 独立运行，互不影响。可同时启动。

---

### 16. 不做的事情

- 不做用户认证（本地工具）
- 不做多轮对话历史（单次问答）
- 不做文档删除管理（通过命令行手动管理）
- 不引入前端构建工具或 npm

---

## 第三部分：核心原理详解

---

### 17. 文档切片原理

**为什么要切片？**

向量检索模型有输入长度限制，且短文本的语义表达更精准。一篇 10 页的 PDF 直接向量化，检索效果会很差。切成小块后：
- 每块语义集中，embedding 向量更有代表性
- 检索时能精确定位到相关段落，而非返回整篇文档

**滑动窗口算法：**

```
配置: CHUNK_SIZE=500, CHUNK_OVERLAP=50
滑动步长 = CHUNK_SIZE - OVERLAP = 450

原始文本（1200 字符）：
|========================== 1200 chars ==========================|

Chunk 0: |------- 500 chars -------|
Chunk 1:                       |------- 500 chars -------|
Chunk 2:                                             |--- 200 --|
                               ↑                     ↑
                          重叠 50 字符           重叠 50 字符
```

**重叠的意义：** 防止关键信息被切在两个 chunk 的边界处丢失。

```
无重叠：  "员工每年享有10天" | "带薪年假，需提前3天申请"  ← 切断了
有重叠：  "员工每年享有10天带薪年假，需提"
                  "10天带薪年假，需提前3天申请"         ← 至少一个chunk完整包含
```

**当前实现的局限：**
- 按字符数切，不按语义切（可能在句子中间断开）
- page 始终为 0（PDF 逐页提取但拼接后丢失页码）
- 无递归分割（LangChain 等框架会先按段落→句子→字符逐级分割）

---

### 18. 语义检索原理（混合模式）

**核心思想：** 本项目使用**混合检索**——同时走两条路径，各取所长：

```
语义检索：  "员工假期多少天" → 命中"年假政策：10天带薪休假"（语义相近，无需共同关键词）
关键词检索："EMP001"         → 精确命中含该工号的 chunk（向量语义无法可靠匹配标识符）

两路结果通过 RRF 融合排序，兼顾语义理解和关键词精确匹配。
```

**完整检索流程：**

```
用户输入: "员工假期有多少天"
         │
         ▼
┌─────────────────────────────┐
│  1. Embedding（向量化）       │  embedder.embed(["员工假期有多少天"])
│  模型: MiniLM-L12-v2        │  → 384 维浮点数数组
│  参数量: 33M（小模型）        │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  2. 向量相似度搜索（纯算法） │  store.search(query_embedding, top_k=5)
│  余弦相似度 + HNSW 索引     │  纯数学计算，无需任何模型
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  3. 返回最相近的 chunks      │  → [{text, source, score}, ...]
└─────────────────────────────┘
```

---

### 19. 三步各需要什么能力

```
步骤                    需要什么             本项目用什么
──────────────────────────────────────────────────────────────
文本 → 向量            Embedding 模型        sentence-transformers（小模型，33M参数）
向量 → 找最近的        纯数学计算 + 索引      ChromaDB（HNSW 算法，点积+排序）
片段 → 生成答案        LLM 大语言模型         Claude（数千亿参数）
```

**关键区分：**

| | Embedding 模型（小模型） | LLM（大模型） |
|---|---|---|
| 本项目 | `MiniLM-L12-v2` | `claude-sonnet-4-6` |
| 参数量 | ~3300 万 | 数千亿 |
| 输入 | 文本 | 文本 |
| 输出 | 固定长度数字数组（384个浮点数） | 自然语言文本 |
| 能力 | 只做一件事：文本→向量 | 理解、推理、生成、对话 |
| 能否对话 | 不能 | 能 |

**"找最近的"为什么不需要模型？**

```
余弦相似度计算 = 两个向量做点积（对应维度相乘再求和）

Q  = [0.12, -0.03, 0.87, 0.45]     ← 查询向量
V0 = [0.11, -0.02, 0.85, 0.44]     ← 某个 chunk 的向量

sim(Q, V0) = 0.12×0.11 + (-0.03)×(-0.02) + 0.87×0.85 + 0.45×0.44
           = 0.0132 + 0.0006 + 0.7395 + 0.198
           = 0.9513

就是乘法和加法，然后排序取 top-k。小学数学就能做。
```

HNSW 是索引数据结构（类似数据库 B-tree），让百万级向量不用逐一比较就能快速定位到"附近"的向量，也是纯算法。

---

### 20. LLM 为什么能把检索片段加工成答案

**本质：** LLM 的核心是"给定上文，预测下一个 token 的概率"。RAG 场景中，答案已经在 prompt 里了，LLM 只需要做阅读理解：

```
RAG Prompt 结构：
┌──────────────────────────────────────────┐
│ 指令: "根据片段回答，不要编造"              │  ← 约束行为
│                                          │
│ [1] 来源：hr.txt                         │
│ 员工每年享有10天带薪年假...                │  ← 答案在这里
│                                          │
│ 问题：年假有多少天？                       │  ← 明确的问题
└──────────────────────────────────────────┘

LLM 做三件事：
  1. 定位：哪段文字和问题相关
  2. 提取：关键信息是什么
  3. 重组：用自然语言表达出来
```

LLM 不需要"记住"任何知识——知识由检索提供。它只负责理解和表达。

**为什么不直接让 LLM 回答（不用 RAG）？**

| | 纯 LLM | RAG (检索 + LLM) |
|---|---|---|
| 知识来源 | 训练数据（固化、可能过时） | 你的文档（实时、可控） |
| 幻觉风险 | 高（编造看似合理的答案） | 低（限定只用提供的片段） |
| 可追溯 | 无法溯源 | 明确知道答案来自哪个文件 |
| 私有数据 | 不知道 | 能回答（索引了就行） |

---

### 21. 整体类比

```
检索 = 图书馆员帮你找到相关的几页书（Embedding + ChromaDB）
LLM  = 读过万卷书的人，读完这几页后用自己的话给你讲明白（Claude）

图书馆员不理解内容（纯数学匹配）
读书人不需要自己藏书（知识由检索提供）
两者配合 = RAG
```

---

## 第四部分：组织图谱模块

---

### 22. 组织图谱目标

通过 lakehouse API 获取生产环境人员数据（在职 ~28,000 人），构建内存图数据结构，实现：

1. **可视化组织图谱** — vis.js 力导向图，交互式探索人员关系网络
2. **关系查询** — 查某人的上级链/下属树/同部门同事
3. **路径分析** — 查两人之间的汇报路径、共同上级
4. **自然语言问答** — "张三的部门负责人是谁"，LLM 转图查询返回结果

---

### 23. 数据源

**数据集：** `it_oa_userlevels`  
**服务：** `it-oa-datalakeinternal`  
**数据量：** 在职 ~28,000 条（全量 ~100,000 条，仅加载在职）  
**获取方式：** 通过 lakehouse API `query_dataset` 分页拉取（limit=10000，约 3 次请求）  
**实际规模：** 28,235 节点，106,162 边，278 个部门

**节点属性字段：**

| 字段 | 含义 | 用途 |
|------|------|------|
| `empno` | 工号 | 节点唯一 ID |
| `empname` | 姓名 | 显示名称 |
| `enname` | 英文名 | 搜索辅助 |
| `loginname` | AD 账号 | 搜索辅助 |
| `deptname` | 部门名称 | 显示/分组 |
| `divname` | 体系名称 | 显示/着色 |
| `engroup` | 业务群 | 顶层分组 |
| `jobname` | 岗位名称 | 详情展示 |

**关系字段（边）：**

| 字段 | 含义 | 边类型 |
|------|------|--------|
| `directsuperior` | 直属上级工号 | `REPORTS_TO` |
| `secondsuperior` | 第二上级工号 | `SECOND_REPORTS_TO` |
| `foreman` | 班组长工号 | `FOREMAN` |
| `f045` | 部门第一负责人工号 | `DEPT_HEAD` |
| `f046` | 体系负责人工号 | `DIV_HEAD` |

---

### 24. 技术选型

| 模块 | 技术 | 理由 |
|------|------|------|
| 图数据结构 | NetworkX (MultiDiGraph) | 纯 Python，3 万节点毫无压力，支持同一对节点间多种边类型 |
| 数据拉取 | 复用 lakehouse client | 已有封装，直接调用 |
| Web 路由 | FastAPI（复用 web_app.py） | 内嵌现有应用 |
| 前端可视化 | vis.js (vis-network) | CDN 引入，力导向布局，交互丰富 |
| 自然语言 | Claude API (function calling) | 将图查询函数暴露为工具，LLM 自动选择调用 |

---

### 25. 架构设计

**目录结构：**

```
knowledge-server/
├── lakehouse/                   ← 共享数据湖仓 API（graph 模块依赖此模块）
│   └── ...
├── graph/
│   ├── __init__.py              ← 模块初始化，暴露 graph_manager 单例
│   ├── loader.py                ← 分页拉取 + 本地 JSON 缓存 + GraphManager（from lakehouse import query_dataset）
│   ├── builder.py               ← 原始数据 → NetworkX MultiDiGraph
│   ├── query.py                 ← 图查询函数（搜索/上下级链/路径/统计）
│   ├── nl_query.py              ← 自然语言 → Claude function calling → 图查询
│   └── .employees_cache.json    ← 本地数据缓存（不提交 git）
├── templates/
│   ├── graph.html               ← 可视化主页
│   └── graph_ask.html           ← 自然语言问答页
├── static/
│   └── graph.js                 ← vis.js 交互逻辑
└── web_app.py                   ← /graph/* 路由组
```

**数据流：**

```
[手动刷新]
lakehouse API (query_dataset, tgt_svc="it-oa-datalakeinternal")
    → 分页拉取（3 次，每次 10000 条）
    → 过滤 hrstatus=在职
    → 写入本地缓存 graph/.employees_cache.json
    → builder.py 构建 NetworkX MultiDiGraph
    → 缓存到内存

[应用启动]
graph/.employees_cache.json → builder.py → 内存图（<1 秒）

[用户查询]
浏览器请求 → FastAPI 路由 → graph/query.py → NetworkX 计算 → JSON 响应 → vis.js 渲染

[自然语言问答]
用户问题 → nl_query.py → Claude (tools=图查询函数列表) → 自动调用 query.py → 结果 → Claude 生成自然语言答案
```

**两级缓存策略：**

```
graph/.employees_cache.json  ← 本地 JSON 文件（持久化，重启免拉取）
         ↓ 启动时自动加载
GraphManager._graph           ← 内存中的 NetworkX 图（毫秒级查询）
```

- **应用启动时**：自动从本地 JSON 缓存加载图（<1 秒），无需访问 API
- **无缓存时**：页面提示用户点击"刷新数据"按钮
- **点击"刷新数据"**：从 API 重新拉取 → 更新本地 JSON → 重建内存图

---

### 26. 图查询接口

```python
def search_person(G, keyword: str) -> list[dict]
def get_superior_chain(G, empno: str) -> list[dict]
def get_subordinates(G, empno: str, depth: int = 1) -> list[dict]
def get_neighbors(G, empno: str, depth: int = 2, max_nodes: int = 80) -> dict
def find_path(G, from_empno: str, to_empno: str) -> list[dict]
def find_common_superior(G, empno_a: str, empno_b: str) -> dict | None
def get_dept_members(G, deptname: str) -> list[dict]
def get_dept_members_by_no(G, deptno: str, deptnosap: str = "") -> list[dict]
def get_stats(G) -> dict
```

---

### 27. Web 路由

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/graph` | 可视化主页 |
| GET | `/graph/ask` | 自然语言问答页 |
| GET | `/graph/api/search?q=张三` | 搜索人员 |
| GET | `/graph/api/neighbors?id=xxx&depth=2` | N 层关系网络 |
| GET | `/graph/api/chain?id=xxx&direction=up` | 上级/下属链 |
| GET | `/graph/api/path?source=A&target=B` | 最短路径 |
| GET | `/graph/api/dept?name=xxx` | 按名称查部门成员 |
| GET | `/graph/api/dept?no=xxx&sap=xxx` | 按编号查部门成员 |
| GET | `/graph/api/dept-tree` | 部门层级树数据 |
| POST | `/graph/api/dept-tree/refresh` | 刷新部门层级数据 |
| GET | `/graph/api/stats` | 统计概览 |
| GET | `/graph/api/ask?q=xxx` | NL 问答 |
| POST | `/graph/api/refresh` | 手动刷新图数据 |

---

### 28. 自然语言问答设计

使用 Claude function calling，将 8 个图查询函数暴露为工具，LLM 根据用户问题自动决定调用哪个函数。支持最多 5 轮工具调用（如先搜索再查链）。完整调用链打印到服务器日志（stderr）。

**工具列表：**

| 工具名 | 功能 |
|--------|------|
| `search_person` | 根据姓名/工号/英文名模糊搜索人员 |
| `get_superior_chain` | 获取完整上级汇报链 |
| `get_subordinates` | 获取直属下属（可指定深度） |
| `find_path` | 查找两人之间最短汇报路径 |
| `find_common_superior` | 查找两人最低共同上级 |
| `get_dept_members` | 按部门名称查成员 |
| `get_dept_members_by_no` | 按部门编号查成员（deptno/deptnosap 任意一种均可，自动通过部门树解析双编号） |
| `get_stats` | 组织图谱统计信息 |

**示例：**

| 用户问题 | LLM 操作 | 返回 |
|----------|----------|------|
| "张三的直属上级是谁" | search_person → get_superior_chain | "张三的直属上级是李四（财务总监）" |
| "财务部有多少人" | get_dept_members → count | "财务部在职人员共 45 人" |
| "部门编号 50012345 有多少人" | get_dept_members_by_no → count | "该部门在职 28 人" |
| "张三和王五的共同上级" | search × 2 + find_common_superior | "最低共同上级是赵六（VP）" |

---

### 29. 前端可视化

- 使用 vis.js (vis-network) CDN，力导向布局
- 节点颜色按体系 (divname) 区分，大小按直属下属数量
- 点击节点显示侧边栏详情，双击节点重新以该节点为中心加载
- `max_nodes=80` 限制防止大图卡死浏览器
- 同一对节点间只保留最高优先级边（减少重叠渲染）

---

### 30. 实施记录（2026-06-02 ~ 06-03）

**关键设计决策变更：**

| 原计划 | 实际 | 原因 |
|--------|------|------|
| DiGraph | **MultiDiGraph** | 同一对节点间存在多种关系，DiGraph 会覆盖 |
| 无节点数限制 | **max_nodes=80** | 高层管理者 depth=2 可达数千节点，vis.js 无法渲染 |
| 所有边都展示 | **同一对节点只保留最高优先级边** | 减少 vis.js 重叠边渲染压力 |
| TTL 自动刷新 | **本地 JSON 缓存 + 手动刷新** | 人员变动低频，启动速度从 5s → <1s |
| 懒加载 | **启动时自动从缓存加载** | 用户体验更好，打开页面即可搜索 |

**实际数据规模：** 28,235 人 / 106,162 边 / 278 部门 / 缓存文件 ~15MB / 从缓存加载 <1 秒

---

### 31. 不做的事情

- 不做编辑功能（数据来自生产系统，只读）
- 不做历史版本对比（不加载离职人员）
- 不做权限控制（本地学习工具）
- 不做全图一次性渲染（性能原因，只做局部展示）

---

## 第五部分：Lakehouse 数据湖仓模块

---

### 32. Lakehouse 模块目标

将 Envision 数据湖仓 REST API 封装为独立模块，支持**双形态**：
- **函数调用**：`from lakehouse import query_dataset, get_dataset_fields` — 供内部模块（如 graph/loader.py）直接 import
- **MCP Server**：`python lakehouse/server.py` → SSE 模式独立运行，供外部 AI Agent 连接

---

### 33. Lakehouse API 函数

| 函数 | 参数 | 说明 |
|------|------|------|
| `query_dataset` | `tgt_svc`, `dataset_name`, filters, fields, sort, limit, offset | 按条件查询数据集记录 |
| `get_record` | `tgt_svc`, `dataset_name`, `caspian_id` | 按唯一 ID 获取单条记录 |
| `list_datasets` | 无 | 列出当前应用下所有数据集（用 Catalog API） |
| `get_dataset_fields` | `dataset_name` | 查询数据集字段结构（字段名/类型/说明/样例） |

**tgt_svc 体系：**

| 配置项 | 用途 | 默认值 |
|--------|------|--------|
| `LIGHTNING_DATA_SVC` | 当前应用自身数据集 | `it-lightning-datalakeprivate` |
| `OA_DATA_SVC` | OA 跨应用授权数据集 | `it-oa-datalakeinternal` |
| `DATALAKE_TGT_SVC` | Catalog API（list/describe） | `it-datalake-api` |

---

### 34. Token 管理

`lakehouse/auth.py` 中的 `TokenManager`：
- 按 `tgt_svc` 分别缓存 token
- 过期前 60 秒主动刷新
- 全局单例 `token_manager`

---

### 35. MCP Server 工具

`lakehouse/server.py` 暴露 4 个 MCP 工具（与函数一一对应）：

| MCP 工具 | 对应函数 | 说明 |
|----------|----------|------|
| `query_dataset` | `client.query_dataset` | filters 参数为 JSON 字符串 |
| `get_record` | `client.get_record` | 按 caspian_id 取记录 |
| `list_datasets` | `client.list_datasets` | 无参数 |
| `describe_dataset` | `client.get_dataset_fields` | 返回字段结构 |

**传输协议：**
- SSE（默认）：`python lakehouse/server.py` → `http://localhost:8000/sse`
- stdio（可选）：`python lakehouse/server.py stdio` — 供 Claude Desktop 等直接启动

---

### 36. Web App 布局设计（2026-06-03 重构）

页面采用**左右布局**，菜单命名采用"动词+对象"风格：

```
┌──────────┬──────────────────────────────────────┐
│ Knowledge│                                      │
│          │         主内容区域                    │
│ 知识库    │                                      │
│  · 问知识  │   （各页面内容在此渲染）              │
│  · 搜文档  │                                      │
│  · 传文件  │                                      │
│          │                                      │
│ 组织架构  │                                      │
│  · 查关系  │                                      │
│  · 问组织  │                                      │
│  · 看部门  │                                      │
│          │                                      │
└──────────┴──────────────────────────────────────┘
```

- 左侧固定宽度（200px）侧边栏，分组显示菜单
- 右侧自适应主内容区
- 当前页面菜单项高亮显示
- 全局 `base.html` 统一布局，子模板只需填充 content block
- 页面 h1 标题与菜单名称保持一致

---

## 第六部分：混合检索（向量 + BM25）

---

### 37. 混合检索目标

纯向量语义检索对关键词精确匹配表现不佳（如工号、专有名词、简短查询），引入 BM25 关键词路径互补：

```
纯向量：  "EMP001" → 可能匹配到语义相近但无关的结果
混合：    "EMP001" → BM25 精确命中含该字符串的 chunk → 排在前面
```

---

### 38. 技术选型

| 模块 | 方案 | 理由 |
|------|------|------|
| BM25 实现 | `rank_bm25.BM25Plus` | 比 BM25Okapi 对零频词处理更优，纯 Python |
| 中文分词 | `jieba` | 轻量，支持新词发现，足够原型需求 |
| 融合算法 | Reciprocal Rank Fusion (RRF) | 无需训练、无需归一化分数，按排名融合 |

---

### 39. 架构设计

```
用户查询
    │
    ├──────────────────────────────────────────────┐
    │                                              │
    ▼                                              ▼
┌────────────────────────┐        ┌────────────────────────┐
│  向量路（权重 0.7）      │        │  BM25 路（权重 0.3）     │
│  embed → ChromaDB       │        │  jieba 分词 → BM25Plus  │
│  返回 top-20 候选       │        │  返回 top-20 候选        │
└────────────────────────┘        └────────────────────────┘
    │                                              │
    └────────────────┐    ┌────────────────────────┘
                     ▼    ▼
            ┌─────────────────────────┐
            │  RRF 融合               │
            │  score = w / (k + rank) │
            │  按 text 去重后合并排序   │
            │  归一化到 [0, 1]         │
            └─────────────────────────┘
                     │
                     ▼
              返回 top-k 结果
```

**RRF 公式：** `rrf_score(doc) = Σ weight_i / (k + rank_i)`，其中 `k=60`（平滑常数）

---

### 40. BM25 索引同步策略

```
写入路径（与 ChromaDB 同步）：
  store.upsert(chunks, embeddings)
      → 写入 ChromaDB
      → bm25_store.add(chunks)  ← 追加到 BM25 语料并重建索引

启动路径（从 ChromaDB 恢复）：
  web_app.py 启动
      → bm25_store.rebuild_from_chroma()  ← 全量同步，保证一致性
```

---

### 41. 降级策略

| 场景 | 行为 |
|------|------|
| BM25 索引为空 | 退化为纯向量检索（返回 vec_results[:top_k]） |
| ChromaDB 为空 | 两路都无结果，返回空列表 |
| jieba 分词结果为空（全标点输入） | BM25 路返回空，退化为纯向量 |

---

## 第七部分：后续扩展方向

- [x] ~~混合检索（向量 + BM25 关键词）~~ ✅ 2026-06-03
- [ ] 支持内网系统（Confluence / SharePoint）作为文档来源
- [ ] `dlake knowledge ingest / ask` CLI 子命令
- [ ] 向量库迁移到 Milvus（生产环境）
- [ ] 文档更新检测（基于文件 mtime，避免重复索引）
- [ ] Web App 多轮对话历史
- [ ] Web App 文档删除管理
- [ ] Reranker 精排（BGE-reranker / Cohere）
- [ ] 分词词典维护（公司专有名词）

---

## 快速参考

```bash
cd knowledge-server

# 索引文档
C:/1AI/.pvenv/Scripts/python.exe ingest.py

# 启动 Web App（端口 8080，浏览器访问）
C:/1AI/.pvenv/Scripts/python.exe web_app.py

# 启动 Knowledge MCP Server（端口 8001，文档检索/问答）
C:/1AI/.pvenv/Scripts/python.exe server.py

# 启动 Lakehouse MCP Server（端口 8000，数据湖仓查询）
C:/1AI/.pvenv/Scripts/python.exe lakehouse/server.py

# 运行所有单元测试
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/ -v

# 导出部门树到 JSON（供离线/静态使用）
C:/1AI/.pvenv/Scripts/python.exe graph/export_departments.py --env uat

# 三者可同时运行，互不影响
```
