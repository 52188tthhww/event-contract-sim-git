"""
全局应用状态（内存）
"""
from config import INITIAL_BALANCE, CONTRACT_DURATIONS, POSITION_SIZE

app_state = {
    "status": "PAUSED",          # PAUSED / RUNNING
    "prices": {},                # symbol → float
    "locked": {d: [] for d in CONTRACT_DURATIONS},  # duration → [strategy_dict, ...]
    "open_positions": [],        # list of position dicts
    "balance": INITIAL_BALANCE,
    "position_size": POSITION_SIZE,  # 每笔交易金额
    "last_reports": [],          # list of {symbol, reports}
    "events": [],                # list of {level, msg, ts}
    "pending_confirm": None,     # 待确认异常消息 (str | None)
    # 自动锁定策略（前端可控参数）
    "auto_lock": {
        "enabled": False,
        "symbol": "BTC_USDT",
        "active_durations": [],
        # 前端可配置参数
        "backtest_hours": [1, 2],       # 回测窗口(小时)，先1h再2h
        "win_rate_threshold": 0.80,     # 胜率门槛
        "min_trades": 10,               # 最少交易笔数
        "loss_streak_enabled": True,    # 连亏切换开关
        "loss_streak_max": 2,           # 连亏触发数
        "reverse_mode": False,          # 反向模式：True=找≤阈值, False=找≥阈值
        "durations": {d: {        # 每个时长独立追踪
            "active_strategy": None,
            "trade_count": 0,
            "win_count": 0,
            "loss_streak": 0,
            "last_trade_pnl": None,
            "status": "idle",
            "_closed_snapshot": 0,
        } for d in CONTRACT_DURATIONS},
    },
}
