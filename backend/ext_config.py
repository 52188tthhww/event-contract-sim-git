"""
扩展配置 — 观测池 + 新策略所需参数，不修改原始 config.py
"""
# 观测池信号计算 K 线粒度（按合约时长）
SIGNAL_BAR_SECONDS = {3: 15, 5: 60, 10: 60}

# 回测：1s→15s 重采样参数
BACKTEST_LOOKBACK_MINUTES = 180
MANUAL_BACKTEST_MAX_HOURS = 4

# 观测池 K 线
OBS_SYMBOL = "BTC_USDT"
OBS_15S_MINUTE_WINDOW = 60
OBS_1M_LIMIT = 120
OBS_POLL_INTERVAL = 2
