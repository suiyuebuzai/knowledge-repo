# Knowledge-Server 企业级演进路线

**创建时间：** 2026-06-02  
**目的：** 从当前原型出发，规划企业级知识库应用的完整技术图景，覆盖 AI 应用开发的方方面面

---

## 1. 当前原型 vs 企业级目标

| 维度 | 当前原型 | 企业级目标 |
|------|----------|-----------|
| 用户规模 | 单人本地 | 数百~数千并发用户 |
| 文档规模 | 几十份 | 数十万份，TB 级 |
| 数据来源 | 本地文件夹 | Confluence/SharePoint/邮件/数据库/API |
| 可用性 | 手动启停 | 7×24 高可用，自动故障恢复 |
| 安全 | 无认证 | SSO + RBAC + 数据分级 + 审计 |
| 质量保障 | 人工感知 | 自动化评估 + A/B 测试 + 可观测性 |
| 部署 | 单机 python 直接运行 | 容器编排 + CI/CD + 多环境 |

---

## 2. 企业级架构全景

```
┌─────────────────────────────────────────────────────────────────────┐
│  接入层 (Gateway)                                                    │
│  API Gateway + 认证(SSO/JWT) + 限流 + 负载均衡                       │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│  应用层                                                              │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────────┐ │
│  │ Web App  │  │ MCP Server│  │ REST API  │  │ Agent Orchestrator│ │
│  │ (前端)   │  │ (AI Agent)│  │ (集成)    │  │ (多步推理)        │ │
│  └──────────┘  └───────────┘  └───────────┘  └───────────────────┘ │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│  核心服务层                                                          │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │ 检索引擎 │  │ 生成服务  │  │ 索引管线 │  │ 知识图谱服务       │ │
│  │ (混合检索│  │ (RAG+流式)│  │ (ETL)    │  │ (实体/关系)        │ │
│  │  +精排)  │  │           │  │          │  │                    │ │
│  └──────────┘  └───────────┘  └──────────┘  └────────────────────┘ │
└──────────────┬──────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│  存储层                                                              │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 向量库   │  │ 图数据库  │  │ 对象存储 │  │ 关系数据库│          │
│  │ (Milvus) │  │(NebulaGraph)│ │ (S3/MinIO)│ │(PostgreSQL)│         │
│  └──────────┘  └───────────┘  └──────────┘  └──────────┘          │
└─────────────────────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────┐
│  基础设施层                                                          │
│  容器编排(K8s) + CI/CD + 监控告警 + 日志收集 + 配置中心              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 各层详细拆解

### 3.1 文档处理管线（Data Pipeline）

企业级文档处理不是简单的"解析+分块"，而是一条完整的 ETL 管线：

```
数据源 → 采集 → 解析 → 清洗 → 分块 → 增强 → 向量化 → 写入 → 质检
```

| 环节 | 当前实现 | 企业级要求 |
|------|----------|-----------|
| **采集** | 手动放文件 | 连接器：Confluence API / SharePoint Graph API / 邮件 IMAP / 网页爬虫 / S3 监听 |
| **解析** | pypdf + python-docx | Unstructured.io（统一 20+ 格式）/ Textract(AWS) / Document AI(GCP) |
| **清洗** | 无 | 去重、去水印、去页眉页脚、Unicode 规范化、PII 脱敏 |
| **分块** | 固定字符窗口 | 语义分块（按段落/标题层级）+ 父子关系保留 |
| **增强** | 无 | LLM 生成摘要、提取元数据（作者/日期/主题）、生成假设问题(HyDE) |
| **向量化** | 本地 MiniLM | 多模型 ensemble / 大模型 Embedding / 领域微调 |
| **写入** | ChromaDB 直接写 | 消息队列解耦（Kafka/RabbitMQ）+ 批量写入 + 失败重试 |
| **质检** | 无 | 自动检测低质量 chunk（过短/乱码/重复）、采样人工审核 |

**关键设计模式：**

```python
# 企业级管线设计（概念示意）
class DocumentPipeline:
    def __init__(self):
        self.connectors = [ConfluenceConnector(), SharePointConnector(), S3Connector()]
        self.parser = UnstructuredParser()
        self.cleaner = DocumentCleaner(remove_pii=True, normalize_unicode=True)
        self.chunker = SemanticChunker(strategy="recursive", respect_headings=True)
        self.enricher = MetadataEnricher(model="gpt-4o-mini")
        self.embedder = EmbeddingService(model="text-embedding-3-large", batch_size=100)
        self.store = MilvusStore(collection="knowledge", partition_key="department")
        self.quality_gate = QualityChecker(min_length=50, max_duplicate_ratio=0.3)

    async def process(self, source: DataSource):
        documents = await source.fetch_updated()          # 增量拉取
        for doc in documents:
            parsed = self.parser.parse(doc)               # 统一解析
            cleaned = self.cleaner.clean(parsed)          # 清洗
            chunks = self.chunker.chunk(cleaned)          # 语义分块
            chunks = self.enricher.enrich(chunks)         # 元数据增强
            chunks = self.quality_gate.filter(chunks)     # 质检过滤
            embeddings = await self.embedder.embed(chunks) # 批量向量化
            await self.store.upsert(chunks, embeddings)   # 写入向量库
```

**学习要点：**
- 连接器模式（Connector Pattern）
- 消息队列解耦（生产者/消费者）
- 幂等性设计（重复执行不产生副作用）
- 背压控制（大量文档时不打爆下游）

---

### 3.2 检索引擎（Retrieval Engine）

企业级检索不是单一的向量搜索，而是多路召回 + 融合排序：

```
用户查询
    │
    ├──→ 查询理解（意图识别 + 查询改写 + 查询扩展）
    │
    ├──→ 多路召回
    │     ├── 向量检索（语义匹配）
    │     ├── BM25 全文检索（关键词匹配）
    │     ├── 知识图谱检索（关系遍历）
    │     └── 元数据过滤（时间/部门/文档类型）
    │
    ├──→ 融合排序（RRF / 加权融合）
    │
    ├──→ Reranking 精排（交叉编码器）
    │
    └──→ 后处理（去重、上下文扩展、权限过滤）
```

| 模块 | 当前 | 企业级 | 技术选型 |
|------|------|--------|----------|
| **查询理解** | 无 | 意图分类 + HyDE 改写 + 同义词扩展 | LLM + 自定义分类器 |
| **向量检索** | ChromaDB top-k | Milvus 分区检索，支持百亿向量 | Milvus / Zilliz Cloud |
| **全文检索** | 无 | BM25 倒排索引 | Elasticsearch / Meilisearch |
| **图检索** | 无 | Cypher 查询实体关系 | NebulaGraph / Neo4j |
| **融合排序** | 无 | Reciprocal Rank Fusion (RRF) | 自研 |
| **精排** | 无 | 交叉编码器重排序 | BGE-Reranker / Cohere Rerank |
| **权限过滤** | 无 | 按用户 ACL 过滤结果 | 向量库 metadata + 业务逻辑 |

**查询理解示例：**

```
原始查询: "去年Q3销售怎么样"
    → 意图识别: 数据查询（非文档检索）→ 路由到 lakehouse
    
原始查询: "合同续签流程"
    → 意图识别: 文档检索
    → HyDE 改写: "合同到期后，甲方或乙方需提前30天书面通知..."（假设答案）
    → 用假设答案的 embedding 去检索（比问题本身更接近答案的向量空间）
```

**学习要点：**
- Reciprocal Rank Fusion 算法
- HyDE (Hypothetical Document Embeddings)
- 交叉编码器 vs 双编码器的区别
- 查询路由（Router）设计模式

---

### 3.3 生成服务（Generation Service）

从单次调用到生产级 RAG 生成：

| 维度 | 当前 | 企业级 |
|------|------|--------|
| **Prompt 管理** | 硬编码在代码中 | Prompt 模板引擎，版本管理，A/B 测试 |
| **上下文构造** | 简单拼接 chunks | 动态 Context Window 管理，按相关性截断 |
| **流式输出** | 基础 SSE | 结构化流（答案 + 引用 + 置信度 分段推送） |
| **多轮对话** | 无 | 对话历史压缩 + 记忆管理 |
| **幻觉控制** | "只用片段中的信息" | 引用标注 + 忠实度检测 + 无法回答判断 |
| **降级策略** | 返回原始片段 | 多 LLM 降级链（Claude → GPT → 本地模型） |
| **成本控制** | 无 | Token 预算、缓存、小模型预筛 |

**高级 RAG 模式：**

```
┌─────────────────────────────────────────────────────┐
│  Agentic RAG（自适应检索）                           │
│                                                     │
│  LLM 作为 Agent:                                    │
│    1. 分析问题 → 判断需要几次检索                    │
│    2. 第一次检索 → 评估结果是否充分                   │
│    3. 不够 → 改写查询 → 再次检索                     │
│    4. 跨源查询 → 合并结果                            │
│    5. 综合生成答案                                   │
│                                                     │
│  vs 当前: 问题 → 一次检索 → 直接生成                 │
└─────────────────────────────────────────────────────┘
```

**学习要点：**
- Prompt Engineering 进阶（Few-shot、Chain-of-Thought）
- Token 计数与上下文窗口管理
- 对话历史摘要压缩
- LLM 评估 LLM（self-evaluation）

---

### 3.4 知识图谱服务（Knowledge Graph）

将非结构化文本转化为结构化知识网络：

```
文档文本 → NER 实体识别 → 关系抽取 → 图写入 → 图检索 → 结果融合
```

**Schema 设计示例（企业知识库）：**

```
节点类型:
  - Person（姓名、职位、部门）
  - Department（名称、层级）
  - Document（标题、类型、日期）
  - Policy（政策名、生效日期、适用范围）
  - Process（流程名、步骤数）
  - Contract（编号、金额、有效期）

边类型:
  - Person -[属于]-> Department
  - Person -[审批]-> Contract
  - Person -[负责]-> Process
  - Document -[描述]-> Policy
  - Policy -[适用于]-> Department
  - Contract -[关联]-> Person
```

**图数据库选型：**

| | NebulaGraph | Neo4j | Amazon Neptune |
|---|---|---|---|
| 开源 | 是 | 社区版是 | 否 |
| 性能 | 千亿级边，分布式 | 十亿级，单机强 | 托管，中等规模 |
| 查询语言 | nGQL / Cypher | Cypher | Gremlin / SPARQL |
| 部署 | K8s 友好 | Docker/K8s | AWS 托管 |
| 学习曲线 | 中 | 低（生态好） | 中 |
| 适合场景 | 超大规模企业 | 中小规模，快速上手 | AWS 全家桶 |

**学习要点：**
- 图数据库建模思维（vs 关系型数据库）
- NER + 关系抽取（用 LLM 做 few-shot extraction）
- 图遍历查询优化
- 向量检索 + 图检索的融合策略

---

### 3.4.1 NebulaGraph 深度研究

#### 概述

NebulaGraph 是一款开源（Apache 2.0）分布式图数据库，由 vesoft 公司开发，C++ 实现。专为超大规模图（千亿节点/边）设计，采用存储与计算分离架构。

**核心特性：**
- **原生分布式：** 无需分片中间件，数据自动分片（Partition）到多个存储节点
- **存算分离：** Graph Service（计算）+ Storage Service（存储）+ Meta Service（元数据）三层架构
- **线性扩展：** 增加机器即可线性提升存储容量和查询吞吐
- **多图空间：** 一个集群可托管多个图空间（类似数据库的 schema 隔离）
- **nGQL 查询语言：** 类 SQL 语法，同时兼容 openCypher

#### 架构

```
┌───────────────────────────────────────────┐
│  客户端 (nebula3-python / HTTP / Console)  │
└───────────────┬───────────────────────────┘
                │
┌───────────────▼───────────────────────────┐
│  Graph Service (graphd)                    │
│  - 查询解析、优化、执行                     │
│  - 无状态，可水平扩展                       │
│  - 默认端口: 9669                           │
└───────────────┬───────────────────────────┘
                │
┌───────────────▼───────────────────────────┐
│  Storage Service (storaged)               │
│  - Raft 一致性，数据分片存储                │
│  - RocksDB 作为底层 KV 引擎                │
│  - 默认端口: 9779                           │
└───────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────┐
│  Meta Service (metad)                     │
│  - Schema 管理、集群协调、分片映射          │
│  - Raft 高可用，3 节点建议                  │
│  - 默认端口: 9559                           │
└───────────────────────────────────────────┘
```

#### 与 Neo4j 对比

| 维度 | NebulaGraph | Neo4j |
|------|-------------|-------|
| 开源协议 | Apache 2.0（完全开放） | 社区版 GPL / 企业版商用付费 |
| 实现语言 | C++ | Java |
| 架构 | 原生分布式，存算分离 | 单机为主，企业版支持集群 |
| 数据规模 | 千亿级边，PB 级 | 十亿级边（单机受内存限制） |
| 查询语言 | nGQL + openCypher 兼容 | Cypher |
| 性能 | 大规模图遍历优势明显 | 中小规模单机查询快 |
| 社区生态 | 中国社区活跃，文档中文友好 | 全球最大图数据库生态 |
| 学习成本 | 中等（三进程部署较复杂） | 低（单 JAR 即可启动） |
| Python 客户端 | nebula3-python | neo4j (官方) |
| 可视化 | NebulaGraph Studio（Web） | Neo4j Browser / Bloom |

**选型建议：**
- 数据 < 10 亿边、团队小、快速验证 → Neo4j 社区版
- 数据 > 10 亿边、需水平扩展、成本敏感 → NebulaGraph
- 当前项目（~28K 节点）→ NetworkX 内存图足够，未来规模增长时迁移

#### 部署方式

**1. Docker Compose（推荐开发/测试）**

最简单的启动方式，3 分钟内可用：

```bash
git clone https://github.com/vesoft-inc/nebula-docker-compose.git
cd nebula-docker-compose
docker-compose up -d

# 验证
docker-compose ps
# 连接: nebula-console -addr 127.0.0.1 -port 9669 -u root -p nebula
```

默认启动 1 graphd + 1 storaged + 1 metad，适合学习和开发。

**2. 单机 RPM/DEB 安装（Linux）**

```bash
# CentOS 7+ / Ubuntu 18.04+
wget https://github.com/vesoft-inc/nebula/releases/download/v3.8.0/nebula-graph-3.8.0.el7.x86_64.rpm
rpm -ivh nebula-graph-3.8.0.el7.x86_64.rpm

# 启动三个服务
sudo /usr/local/nebula/scripts/nebula.service start all
sudo /usr/local/nebula/scripts/nebula.service status all
```

**3. Kubernetes（生产环境）**

使用 NebulaGraph Operator 部署：

```bash
# 安装 Operator
helm install nebula-operator nebula-operator/nebula-operator

# 部署集群（3 metad + 3 storaged + 3 graphd）
kubectl apply -f nebula-cluster.yaml
```

**4. Windows 本地开发**

NebulaGraph **不原生支持 Windows**。Windows 上的方案：
- **WSL2 + Docker Desktop**（推荐）：在 WSL2 中运行 Docker Compose
- **WSL2 + 原生安装**：在 WSL2 的 Ubuntu 中用 RPM/DEB 安装
- **远程 Linux 服务器**：开发机连接远端 NebulaGraph

```bash
# WSL2 方式（Windows 上推荐）
wsl --install -d Ubuntu-22.04
# 进入 WSL2 后按 Linux Docker Compose 方式部署
```

#### nGQL 查询语言示例

```sql
-- 创建图空间
CREATE SPACE org_graph (vid_type=FIXED_STRING(64), partition_num=10, replica_factor=1);
USE org_graph;

-- 定义 Schema
CREATE TAG person (name string, emp_id string, title string, department string);
CREATE TAG department (name string, level int);
CREATE EDGE reports_to (since datetime);
CREATE EDGE belongs_to ();

-- 插入数据
INSERT VERTEX person (name, emp_id, title, department) VALUES
  "p001":("张三", "EMP001", "工程师", "技术部"),
  "p002":("李四", "EMP002", "经理", "技术部");
INSERT EDGE reports_to (since) VALUES "p001"->"p002":(datetime("2024-01-01"));

-- 查询：张三的直属上级
GO FROM "p001" OVER reports_to YIELD dst(edge) AS boss_id
| GO FROM $-.boss_id OVER reports_to YIELD properties($$).name AS boss_name;

-- 查询：从张三到 CEO 的汇报链
FIND SHORTEST PATH FROM "p001" TO "ceo001" OVER reports_to YIELD path AS p;

-- 查询：技术部所有人
LOOKUP ON person WHERE person.department == "技术部" YIELD vertex AS v;

-- 子图查询：某人 2 跳内的所有关系
GET SUBGRAPH 2 STEPS FROM "p001" BOTH reports_to, belongs_to;
```

#### Python 客户端（nebula3-python）

```bash
pip install nebula3-python
```

```python
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config

# 连接配置
config = Config()
config.max_connection_pool_size = 10

pool = ConnectionPool()
pool.init([("127.0.0.1", 9669)], config)

# 执行查询
with pool.session_context("root", "nebula") as session:
    session.execute("USE org_graph")
    
    # 查询汇报链
    result = session.execute(
        'GO FROM "p001" OVER reports_to YIELD dst(edge) AS boss'
    )
    
    for row in result.rows():
        print(row.values[0].get_sVal())

pool.close()
```

#### 与当前项目的关系

当前组织图谱模块用 NetworkX（内存图）：
- 28K 节点 + ~27K 边 → NetworkX 加载 <1 秒
- 全部数据来自 Envision 数据湖仓 API，每次刷新重建

**何时需要迁移到 NebulaGraph：**
- 节点/边规模超过 100 万（NetworkX 内存占用 >2GB）
- 需要多人并发实时读写图
- 需要持久化存储，不依赖外部数据源实时重建
- 需要复杂图算法（PageRank、社区发现）在数据库层执行
- 需要 ACID 事务保证

**迁移路径：**
```
当前:  Envision API → NetworkX (内存) → query.py 遍历
未来:  Envision API → NebulaGraph (持久化) → nGQL 查询
       graph/query.py 改为调用 nebula3-python 客户端
```

#### 官方文档与参考资源

| 资源 | 地址 | 说明 |
|------|------|------|
| 官方文档 | https://docs.nebula-graph.io/ | 最全面的中英文文档 |
| GitHub 主仓库 | https://github.com/vesoft-inc/nebula | 源码，Issue，Release |
| Docker Compose | https://github.com/vesoft-inc/nebula-docker-compose | 一键部署脚本 |
| Python 客户端 | https://github.com/vesoft-inc/nebula-python | nebula3-python 源码 |
| NebulaGraph Studio | https://github.com/vesoft-inc/nebula-studio | Web 可视化管理工具 |
| nGQL 语法手册 | https://docs.nebula-graph.io/3.8.0/3.ngql-guide/ | 查询语言完整参考 |
| K8s Operator | https://github.com/vesoft-inc/nebula-operator | Kubernetes 部署 |
| 中文论坛 | https://discuss.nebula-graph.com.cn/ | 社区问答 |
| 学习路径 | https://docs.nebula-graph.io/3.8.0/20.appendix/learning-path/ | 官方推荐学习顺序 |

---

### 3.5 安全与权限体系

企业知识库的安全不是"加个登录"这么简单：

```
┌─────────────────────────────────────────────┐
│  安全分层                                    │
│                                             │
│  L1: 认证 (Authentication)                   │
│      → 你是谁？SSO / OAuth2 / SAML          │
│                                             │
│  L2: 授权 (Authorization)                    │
│      → 你能干什么？RBAC / ABAC              │
│                                             │
│  L3: 数据隔离 (Data Isolation)               │
│      → 你能看什么？行级/文档级权限           │
│                                             │
│  L4: 数据脱敏 (Data Masking)                 │
│      → 敏感信息处理。PII 检测+脱敏          │
│                                             │
│  L5: 审计追踪 (Audit Trail)                  │
│      → 你做了什么？全链路日志               │
│                                             │
│  L6: 合规 (Compliance)                       │
│      → 满足法规。GDPR / 等保 / 数据分级     │
└─────────────────────────────────────────────┘
```

**文档级权限控制方案：**

```python
# 索引时标记权限
chunk_metadata = {
    "source": "hr_policy.pdf",
    "department": "HR",
    "classification": "internal",       # public / internal / confidential / secret
    "acl_groups": ["hr_team", "management"],
}

# 检索时过滤
def search_with_acl(query, user):
    user_groups = get_user_groups(user)
    user_clearance = get_clearance_level(user)
    
    results = vector_store.search(
        query_embedding,
        filter={
            "classification": {"$lte": user_clearance},
            "acl_groups": {"$in": user_groups},
        }
    )
```

**学习要点：**
- OAuth2 / OIDC 认证流程
- RBAC vs ABAC 权限模型
- 向量数据库的 metadata 过滤实现权限控制
- PII 检测与脱敏（正则 + NER 模型）

---

### 3.6 可观测性（Observability）

生产系统必须能回答：系统健不健康？用户满不满意？哪里是瓶颈？

```
┌──────────────────────────────────────────────────────────────┐
│  三大支柱                                                     │
│                                                              │
│  Metrics（指标）        Logs（日志）         Traces（链路）     │
│  ├ QPS / 延迟 P99      ├ 结构化 JSON 日志   ├ 请求→检索→LLM   │
│  ├ Token 消耗/成本     ├ 错误堆栈           ├ 各环节耗时       │
│  ├ 检索召回率          ├ 查询历史           ├ 跨服务追踪       │
│  └ 用户满意度(👍👎)    └ 审计记录           └ 瓶颈定位         │
└──────────────────────────────────────────────────────────────┘
```

**RAG 专属指标：**

| 指标 | 含义 | 目标值 |
|------|------|--------|
| Retrieval Latency P99 | 检索延迟 99 分位 | < 200ms |
| Generation Latency P99 | 生成延迟（首 token） | < 2s |
| Retrieval Precision@5 | top-5 中相关结果占比 | > 80% |
| Faithfulness | 答案忠实于检索片段的程度 | > 90% |
| User Satisfaction | 用户点赞/点踩比率 | > 85% |
| Token Cost / Query | 每次查询平均 token 消耗 | 可控预算内 |
| Index Freshness | 文档更新到可检索的延迟 | < 5min |

**技术栈：**
- 指标：Prometheus + Grafana
- 日志：ELK (Elasticsearch + Logstash + Kibana) 或 Loki
- 链路：Jaeger / OpenTelemetry
- RAG 评估：RAGAS / DeepEval / LangSmith

**学习要点：**
- OpenTelemetry 标准接入
- LLM 应用的特殊监控（token 成本、幻觉率）
- 用户反馈闭环（thumbs up/down → 自动标注 → 微调）

---

### 3.7 部署与运维（DevOps / MLOps）

```
代码提交 → CI 测试 → 构建镜像 → 部署到 Staging → 自动化评估 → 上线生产
                                                     ↑
                                              RAG 质量回归测试
```

| 环节 | 技术选型 |
|------|----------|
| 容器化 | Docker（多阶段构建，分离 CPU/GPU 镜像） |
| 编排 | Kubernetes（HPA 自动扩缩容） |
| CI/CD | GitHub Actions / GitLab CI |
| 配置管理 | Vault（密钥）+ ConfigMap（配置） |
| 模型管理 | MLflow / DVC（Embedding 模型版本） |
| 蓝绿部署 | 新旧版本并行，流量切换 |
| 回滚策略 | 向量库快照 + 代码版本绑定 |

**RAG 系统的特殊运维挑战：**

```
传统应用:  代码变更 → 部署 → 验证功能
RAG 应用:  代码变更 / 模型变更 / 数据变更 → 任意一个都可能影响质量
           需要: 回归测试集 + 自动化评估 + 质量门禁
```

**学习要点：**
- Docker 多阶段构建（减小镜像体积）
- K8s 核心概念（Pod、Service、Ingress、HPA）
- GitOps 工作流
- 模型版本与数据版本的绑定管理

---

### 3.8 多模态文档理解

企业文档不只是纯文本：

| 文档类型 | 挑战 | 解决方案 |
|----------|------|----------|
| 扫描件 PDF | 无文字层 | OCR (Tesseract / PaddleOCR / Document AI) |
| 表格 | 结构化信息被拉平 | 表格检测 + 转 Markdown/JSON 保留结构 |
| 流程图/架构图 | 信息在图片中 | Vision LLM 描述图片内容 → 文本化 |
| PPT | 排版复杂，文字分散 | 按 slide 分块，保留标题层级 |
| 邮件 | 线程嵌套，签名干扰 | 邮件解析器 + 签名去除 + 线程展开 |

**技术方案对比：**

| 方案 | 优点 | 缺点 |
|------|------|------|
| Unstructured.io | 开源，支持 20+ 格式统一接口 | 重（依赖多），表格效果一般 |
| AWS Textract | 表格/表单识别强 | 付费，需 AWS 环境 |
| Google Document AI | OCR + 结构理解，多语言 | 付费，需 GCP |
| LlamaParse | LlamaIndex 官方，面向 RAG 优化 | 付费 API |
| PyMuPDF + Vision LLM | 灵活组合 | 需要自己编排 |

---

### 3.9 Agent 编排与多工具协作

从"一问一答"到"自主推理"：

```
简单 RAG:
  用户问题 → 检索一次 → 生成答案

Agentic RAG:
  用户问题 → Agent 规划
    → "需要先查政策文档" → search_documents("年假政策")
    → "信息不够，查一下具体案例" → search_documents("年假申请案例")
    → "还需要组织架构确认审批人" → graph_query("年假审批→谁")
    → 综合三次结果 → 生成完整答案

多 Agent 协作:
  ┌─────────┐     ┌──────────┐     ┌───────────┐
  │ Router  │ ──→ │ Knowledge│     │ Lakehouse │
  │ Agent   │     │ Agent    │     │ Agent     │
  │ (分发)  │ ──→ │ (文档)   │     │ (数据)    │
  └─────────┘     └──────────┘     └───────────┘
       │                                  │
       └────────── Coordinator ───────────┘
                        │
                   最终答案
```

**编排框架对比：**

| 框架 | 特点 | 适合 |
|------|------|------|
| LangChain | 生态最大，组件多 | 快速原型，组合现成组件 |
| LlamaIndex | RAG 专精，索引策略丰富 | 知识密集型应用 |
| CrewAI | 多 Agent 角色扮演 | 复杂任务分工 |
| AutoGen | 微软出品，Agent 对话 | 研究探索 |
| 自研 | 最灵活，无框架锁定 | 生产系统，需要精细控制 |

**学习要点：**
- ReAct (Reasoning + Acting) 模式
- 工具描述对 Agent 决策的影响
- Agent 循环终止条件设计（防无限循环）
- 多 Agent 通信协议

---

## 4. 企业级迭代路线图

### Phase 1：检索质量基线（1-2 周）

| 任务 | 产出 | 学到什么 |
|------|------|----------|
| 语义分块 | 递归分割器，按段落/句子边界切 | NLP 句子切分、chunk 策略对比 |
| BM25 混合检索 | Elasticsearch 或 rank_bm25 库 | 倒排索引原理、TF-IDF |
| Reranking | BGE-Reranker 精排 | 交叉编码器 vs 双编码器 |
| 评估框架 | RAGAS 测试集 + CI 集成 | RAG 质量度量方法论 |

### Phase 2：交互体验（2-3 周）

| 任务 | 产出 | 学到什么 |
|------|------|----------|
| 多轮对话 | 对话历史管理 + 上下文压缩 | Token 管理、摘要策略 |
| 前端升级 | React/Vue SPA，Markdown 渲染 | 现代前端工程化 |
| 文档管理 | CRUD + 索引状态展示 | 全栈 CRUD 开发 |
| 反馈闭环 | 👍👎 按钮 → 标注数据收集 | 用户反馈系统设计 |

### Phase 3：知识深度（3-4 周）

| 任务 | 产出 | 学到什么 |
|------|------|----------|
| 知识图谱 | NER + 关系抽取 + Neo4j | 图建模、LLM 信息抽取 |
| 查询路由 | 意图分类 + 多路分发 | 分类器训练、路由设计 |
| Agentic RAG | 多步检索 Agent | Agent 设计模式 |
| 多模态 | 表格/图片理解 | Vision LLM 应用 |

### Phase 4：工程化（4-6 周）

| 任务 | 产出 | 学到什么 |
|------|------|----------|
| Docker 容器化 | Dockerfile + docker-compose | 容器化最佳实践 |
| 认证授权 | OAuth2 + RBAC + 文档级 ACL | 安全架构 |
| 可观测性 | Prometheus + Grafana + 链路追踪 | 监控体系搭建 |
| CI/CD | GitHub Actions + 自动评估门禁 | DevOps 流程 |
| 向量库迁移 | ChromaDB → Milvus | 分布式系统运维 |

### Phase 5：企业集成（6-8 周）

| 任务 | 产出 | 学到什么 |
|------|------|----------|
| 数据源连接器 | Confluence / SharePoint 对接 | API 集成、OAuth 授权 |
| 增量同步 | Change Data Capture + 消息队列 | 事件驱动架构 |
| 多租户 | 数据隔离 + 租户配置 | SaaS 架构 |
| 管理后台 | 系统配置 + 用户管理 + 用量统计 | 后台系统设计 |

---

## 5. 技术选型决策矩阵

### 5.1 向量数据库

| | ChromaDB | Milvus | Weaviate | Pinecone | pgvector |
|---|---|---|---|---|---|
| 规模 | <10万 | 亿级 | 千万级 | 亿级 | 百万级 |
| 部署 | 嵌入式 | K8s/Docker | Docker | 全托管 | PostgreSQL 插件 |
| 混合检索 | 弱 | 原生支持 | 原生支持 | 有限 | SQL + 向量 |
| 成本 | 免费 | 开源免费 | 开源免费 | 按查询付费 | 免费 |
| 推荐阶段 | 原型/学习 | 生产 | 生产 | 快速上线 | 已有 PG 的团队 |

### 5.2 Embedding 模型

| 模型 | 维度 | 中文支持 | 部署 | 适合 |
|------|------|----------|------|------|
| MiniLM-L12-v2 (当前) | 384 | 支持 | 本地 | 原型，免费 |
| BGE-large-zh-v1.5 | 1024 | 强 | 本地 | 中文场景生产 |
| text-embedding-3-small | 1536 | 支持 | API | 低成本 API 方案 |
| text-embedding-3-large | 3072 | 支持 | API | 最高质量 |
| Cohere embed-v3 | 1024 | 支持 | API | 多语言强 |

### 5.3 LLM 选型

| 场景 | 推荐模型 | 理由 |
|------|----------|------|
| RAG 生成（主力） | Claude Sonnet | 平衡质量与成本 |
| 复杂推理/Agent | Claude Opus | 最强推理能力 |
| 元数据抽取/分类 | Claude Haiku / GPT-4o-mini | 低成本批量任务 |
| 本地部署（无网络） | Qwen-2 / Llama-3 | 隐私要求高 |

---

## 6. 成本估算框架

### 每月运行成本（1000 用户，10 万文档）

| 项目 | 方案 A（最经济） | 方案 B（均衡） | 方案 C（最优质量） |
|------|-----------------|---------------|-------------------|
| LLM 生成 | Claude Haiku ¥500 | Claude Sonnet ¥3,000 | Claude Opus ¥15,000 |
| Embedding | 本地模型 ¥0 | text-embedding-3-small ¥200 | text-embedding-3-large ¥800 |
| 向量库 | ChromaDB(自建) ¥0 | Milvus(自建) ¥500 | Zilliz Cloud ¥2,000 |
| 服务器 | 2C4G ¥200 | 4C16G+GPU ¥1,500 | K8s 集群 ¥5,000 |
| **月总计** | **¥700** | **¥5,200** | **¥22,800** |

---

## 7. 总结：从原型到企业级的跨越

```
你现在在这里
     ↓
[原型] ——→ [质量优化] ——→ [产品化] ——→ [工程化] ——→ [企业级]
  │            │              │             │            │
  │            │              │             │            │
  单文件       智能分块        多轮对话      容器化       多租户
  单用户       混合检索        用户反馈      CI/CD        SSO/RBAC
  手动索引     Reranking      文档管理      监控告警     数据源集成
  纯向量       评估框架        前端 SPA     自动扩缩     合规审计
```

每个阶段都是完整可交付的产品，不需要一步到位。核心原则：**先让检索质量好到用户愿意用，再解决工程和规模问题。**
