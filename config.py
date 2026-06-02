from pathlib import Path

BASE_DIR = Path(__file__).parent

DOCS_DIR    = str(BASE_DIR / "docs_input")
CHROMA_DIR  = str(BASE_DIR / "chroma_db")

EMBED_MODEL  = "paraphrase-multilingual-MiniLM-L12-v2"  # 384 维，支持中文
CLAUDE_MODEL = "claude-sonnet-4-6"

CHUNK_SIZE    = 500   # 每块最大字符数
CHUNK_OVERLAP = 50    # 相邻块重叠字符数（保留上下文）
TOP_K         = 5     # 检索返回 top-k 个 chunk
WEB_PORT      = 8080  # Web 应用端口（环境变量 KNOWLEDGE_WEB_PORT 可覆盖）
