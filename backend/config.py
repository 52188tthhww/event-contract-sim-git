"""
事件合约模拟交易系统 — 全局配置
"""
import os

# 数据源: okx / binance / gateio
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "okx")
OKX_BASE = "https://www.okx.com"
BINANCE_BASE = "https://fapi.binance.com"
GATE_BASE = "https://api.gateio.ws"
DATA_TYPE = "futures"

# 交易品种
SYMBOLS = ["BTC_USDT", "ETH_USDT"]

# 事件合约时长（分钟）
CONTRACT_DURATIONS = [3, 5, 10]

# 调度参数
POLL_INTERVAL = 2          # 价格轮询间隔（秒）
BACKTEST_INTERVAL = 60     # 自动回测间隔（秒）

# 策略筛选阈值
WIN_RATE_THRESHOLD = 0.75  # 最低胜率
MIN_TRADES = 5             # 最少交易次数

# 模拟账户
INITIAL_BALANCE = 10000.0  # 初始资金
POSITION_SIZE = 100.0      # 每笔交易金额 (USDT)

# 数据库
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim.db")

# K 线
CANDLE_INTERVAL = "1m"     # 1 分钟 K 线
DEFAULT_CANDLE_LIMIT = 1440  # 默认拉取 1440 根（24 小时）
