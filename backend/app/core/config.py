import os

# 尝试加载 .env 文件（如果 python-dotenv 可用）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 运行模式: cloud | local
AI_MODE = os.getenv("AI_MODE", "local")

# SiliconFlow 云端配置
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

# 模型名称
OCR_MODEL_CLOUD = os.getenv("OCR_MODEL_CLOUD", "deepseek-ai/DeepSeek-OCR")
LLM_MODEL_CLOUD = os.getenv("LLM_MODEL_CLOUD", "deepseek-ai/DeepSeek-V4-Flash")
OCR_MODEL_LOCAL = os.getenv("OCR_MODEL_LOCAL", "glm-ocr:latest")
LLM_MODEL_LOCAL = os.getenv("LLM_MODEL_LOCAL", "qwen3.6:27b")

MAX_WORKERS_CLOUD = int(os.getenv("MAX_WORKERS_CLOUD", "15"))
MAX_WORKERS_LOCAL = int(os.getenv("MAX_WORKERS_LOCAL", "4"))

# OCR 和 LLM 独立并发数（云端/本地分离，互不阻塞）。
# 云端部署应按服务商公开限额和自己的账户策略显式配置。
OCR_MAX_WORKERS_CLOUD = int(os.getenv("OCR_MAX_WORKERS_CLOUD", "4"))
LLM_MAX_WORKERS_CLOUD = int(os.getenv("LLM_MAX_WORKERS_CLOUD", "6"))
OCR_MAX_WORKERS_LOCAL = int(os.getenv("OCR_MAX_WORKERS_LOCAL", "4"))
LLM_MAX_WORKERS_LOCAL = int(os.getenv("LLM_MAX_WORKERS_LOCAL", "6"))

# 后台任务队列。每个 worker 处理一个任务，任务内再按 OCR/LLM 并发控制。
JOB_QUEUE_WORKERS = int(os.getenv("JOB_QUEUE_WORKERS", "3"))
# 同一个父批量任务最多同时运行几个子批次，防止 2 万张大任务独占全部队列 worker。
MAX_ACTIVE_CHILDREN_PER_PARENT = int(os.getenv("MAX_ACTIVE_CHILDREN_PER_PARENT", "1"))

# SiliconFlow 限额可能按账号、模型、RPM 和 TPM 等维度触发。
# 这些值只是可覆盖的运行默认值，不代表任何特定账户的实际额度。
SILICONFLOW_OCR_RPM = int(os.getenv("SILICONFLOW_OCR_RPM", "1000"))
SILICONFLOW_LLM_RPM = int(os.getenv("SILICONFLOW_LLM_RPM", "500"))
SILICONFLOW_OCR_TPM = int(os.getenv("SILICONFLOW_OCR_TPM", "80000"))
SILICONFLOW_LLM_TPM = int(os.getenv("SILICONFLOW_LLM_TPM", "2000000"))

# 兼容旧配置。>0 时作为没有显式模型桶配置时的兜底 RPM。
SILICONFLOW_CHAT_RPM = int(os.getenv("SILICONFLOW_CHAT_RPM", "0"))
SILICONFLOW_MAX_RETRIES = int(os.getenv("SILICONFLOW_MAX_RETRIES", "5"))
SILICONFLOW_RETRY_DELAYS = os.getenv("SILICONFLOW_RETRY_DELAYS", "5,15,45,120,240")

# LLM 上下文长度限制
LLM_MAX_CONTEXT_CLOUD = int(os.getenv("LLM_MAX_CONTEXT_CLOUD", "8000"))
LLM_MAX_CONTEXT_LOCAL = int(os.getenv("LLM_MAX_CONTEXT_LOCAL", "6000"))

# Ollama 本地配置
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

PRECLASSIFY_THRESHOLD = float(os.getenv("PRECLASSIFY_THRESHOLD", "0.7"))

# 任务整体超时（秒）。asyncio.gather 超时后，已完成文件保留，未完成标记失败
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "7200"))  # 默认 2 小时

# PDF 页面 OCR 并发数（云端连接池 50，设为 8 可充分利用）
PDF_OCR_CONCURRENCY = int(os.getenv("PDF_OCR_CONCURRENCY", "8"))
