"""测试配置常量"""

# 等待时间配置（毫秒）
WAIT_SHORT = 1000
WAIT_MEDIUM = 3000
WAIT_LONG = 5000
WAIT_EXTRA_LONG = 10000

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2000

# 超时配置
PAGE_LOAD_TIMEOUT = 30000
ELEMENT_TIMEOUT = 10000
API_TIMEOUT = 30000

# 日志级别
LOG_LEVEL = "INFO"

# 报告配置
REPORT_DIR = ".runtime/reports"
REPORT_FORMAT = "json"

# 测试环境配置
ENV_LOCAL = "local"
ENV_UAT = "uat"
ENV_PROD = "prod"
