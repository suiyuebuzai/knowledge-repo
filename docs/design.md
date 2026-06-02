# Knowledge 项目完整设计文档

**创建时间：** 2026-05-27（MCP Server）/ 2026-06-02（Web App）  
**状态：** MCP Server ✅ 已完成 / Web App ✅ 已完成  
**定位：** 非结构化文档检索系统，包含 MCP Server（供 AI Agent 调用）+ Web App（供人类浏览器使用）

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
| 生成（ask_document） | `claude-sonnet-4-6` via 公司代理 | 复用现有 ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL |
| MCP Server | FastMCP（复用现有模式） | 和 lakehouse-mcp-server 一致 |

---

### 3. 目录结构

```
knowledge-server/
├── server.py      ← MCP Server（2 个工具）
├── web_app.py     ← FastAPI Web 应用（问答/检索/上传）
├── ingest.py      ← 索引入口，命令行触发
├── retriever.py   ← 检索逻辑，组合 embedder + store
├── chunker.py     ← 文档解析与分块
├── embedder.py    ← sentence-transformers 封装
├── store.py       ← ChromaDB 读写封装
├── config.py      ← 配置常量
├── templates/     ← Jinja2 模板（Web App）
│   ├── base.html
│   ├── ask.html
│   ├── search.html
│   └── upload.html
├── static/        ← 静态资源（Web App）
│   └── style.css
├── docs_input/    ← 待索引文档放这里（不提交 git）
└── chroma_db/     ← 向量库持久化目录（不提交 git）
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

#### retriever.py
```python
def search(query: str, top_k: int = TOP_K) -> list[dict]:
    """query → embed → ChromaDB 检索 → 返回 top-k chunks"""
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
  → store.upsert()             # 写入 ChromaDB（相同 id 覆盖）
```

#### 查询路径（MCP 工具调用）
```
search_documents:
  Claude → retriever.search(query) → embedder + store → 返回 chunks JSON

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

---

### 13. Web App 功能详细设计

#### 13.1 问答页 (`/`)

**页面元素：**
- 文本输入框 + 提交按钮
- 回答展示区域（逐字填充）
- 引用来源列表（回答完成后展示）

**流程：**
1. 用户输入问题，点击"提问"
2. 前端 JS 创建 `EventSource("/ask/stream?q=...")`
3. 后端调用 retriever → 构造 RAG prompt → Claude 流式生成
4. 逐 token 通过 SSE 推送给前端
5. 最后发送来源信息

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

---

### 14. Web App 错误处理

| 场景 | 处理方式 |
|------|----------|
| 知识库为空 | 问答/检索页提示"请先上传文档" |
| Claude API 调用失败 | SSE 发送 `event: error`，前端展示错误 + 原始检索片段降级 |
| 文件格式不支持 | 上传页返回错误提示，不中断其他文件处理 |

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

### 18. 语义检索原理

**核心思想：** 传统搜索是关键词匹配，语义检索是含义匹配——把文本变成数学向量，通过向量间距离衡量语义相似度。

```
传统搜索：  "员工假期多少天" → 搜不到"年假政策：10天带薪休假"（无共同关键词）
语义检索：  "员工假期多少天" → 命中"年假政策：10天带薪休假"（语义相近）
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

## 第四部分：后续扩展方向

- [ ] 支持内网系统（Confluence / SharePoint）作为文档来源
- [ ] `dlake knowledge ingest / ask` CLI 子命令
- [ ] 混合检索（向量 + BM25 关键词）
- [ ] 向量库迁移到 Milvus（生产环境）
- [ ] 文档更新检测（基于文件 mtime，避免重复索引）
- [ ] Web App 多轮对话历史
- [ ] Web App 文档删除管理

---

## 快速参考

```bash
# 索引文档
cd knowledge-server
C:/1AI/.pvenv/Scripts/python.exe ingest.py

# 启动 Web App（端口 8080，供人类浏览器使用）
C:/1AI/.pvenv/Scripts/python.exe web_app.py

# 启动 MCP Server（端口 8001，供 AI Agent 调用）
C:/1AI/.pvenv/Scripts/python.exe server.py

# 两者可同时运行，互不影响
```
