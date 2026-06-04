from pathlib import Path
from dotenv import load_dotenv
import os as _os

BASE_DIR = Path(__file__).parent

# 加载环境变量
_env_file = BASE_DIR / ".env.uat"
if _env_file.exists():
    load_dotenv(_env_file)

DOCS_DIR    = str(BASE_DIR / "docs_input")
CHROMA_DIR  = str(BASE_DIR / "chroma_db")

EMBED_MODEL  = "paraphrase-multilingual-MiniLM-L12-v2"  # 384 维，支持中文
CLAUDE_MODEL = "claude-sonnet-4-6"

CHUNK_SIZE    = 500   # 每块最大字符数
CHUNK_OVERLAP = 50    # 相邻块重叠字符数（保留上下文）
TOP_K         = 5     # 检索返回 top-k 个 chunk
WEB_PORT      = 8080  # Web 应用端口（环境变量 KNOWLEDGE_WEB_PORT 可覆盖）

# ── BM25 混合检索配置 ──
BM25_WEIGHT        = 0.3   # BM25 在 RRF 中的权重（向量权重 = 1 - BM25_WEIGHT）
HYBRID_CANDIDATE_K = 20    # 每路过抓取候选数（融合前）

# ── 图谱模块配置 ──
GRAPH_TTL = 3600          # 图数据缓存 TTL（秒）
GRAPH_DEFAULT_DEPTH = 2   # 默认展开层级

# Lakehouse API 配置（用于拉取人员数据）
ENVISION_BASE_URL = _os.getenv("ENVISION_BASE_URL", "https://platform-uat.envision-io.com")
ENVISION_APP_ID = _os.getenv("LIGHTNING_APP_ID", "")
ENVISION_APP_SECRET = _os.getenv("LIGHTNING_APP_SECRET", "")
ENVISION_USER_ID = _os.getenv("LIGHTNING_USER_ID", "")
OA_DATA_SVC = _os.getenv("OA_DATA_SVC", "it-oa-datalakeinternal")
LIGHTNING_DATA_SVC = _os.getenv("LIGHTNING_DATA_SVC", "it-lightning-datalakeprivate")
DATALAKE_TGT_SVC = _os.getenv("DATALAKE_TGT_SVC", "it-datalake-api")
