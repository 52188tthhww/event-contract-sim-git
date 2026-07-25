"""
事件合约回测引擎
- 按 1m K 线逐根回测
- t 时刻信号 → t 时刻开仓 → t + duration_min 平仓
- 支持 3/5/10 分钟事件合约
"""
from typing import List, Dict
import pandas as pd
from strategies import STRATEGIES
from config import CONTRACT_DURATIONS, WIN_RATE_THRESHOLD, MIN_TRADES


def run_single_backtest(
    df: pd.DataFrame, duration_min: int, strategy: dict, bar_seconds: int = 60
) -> dict:
    """
    对单个策略在指定合约时长上运行回测。

    参数:
        df: K 线 DataFrame（列: time, open, high, low, close, volume）
        duration_min: 事件合约时长（分钟）
        strategy: 策略字典 {id, name, fn, params}
        bar_seconds: 每根 K 线秒数（默认 60=1m）

    返回:
        报表字典，含 trades 明细列表
    """
    # 1. 计算信号
    df = strategy["fn"](df.copy(), strategy["params"])

    # 2. 防止未来函数：信号基于上一根 K 线，shift 后再用
    df["signal"] = df["signal"].shift(1).fillna(0).astype(int)

    # 3. 逐根遍历开仓
    trades = []
    hold = max(1, duration_min * 60 // bar_seconds)  # 持仓 K 线根数
    max_i = len(df) - hold

    from ext_strategies import is_flip_strategy
    _flip = is_flip_strategy(strategy["id"])
    _prev_sig = 0

    for i in range(max_i):
        sig = df["signal"].iloc[i]
        if sig == 0:
            _prev_sig = sig
            continue

        # 持续信号策略：仅翻转时开仓（1→-1 或 -1→1）
        if _flip and sig == _prev_sig:
            continue
        _prev_sig = sig

        # 5/10min 加量确认（15s 量太噪，仅对 1m bar 生效）
        if _flip and bar_seconds == 60:
            vol_ma = df["volume"].rolling(20).mean()
            if df["volume"].iloc[i] <= vol_ma.iloc[i]:
                continue

        entry_price = df["close"].iloc[i]
        exit_price = df["close"].iloc[i + hold]
        pnl = (exit_price - entry_price) * sig  # sig=1 做多, sig=-1 做空
        win = pnl > 0

        trades.append({
            "entry_time": df["time"].iloc[i].isoformat(),
            "entry_price": round(entry_price, 4),
            "direction": "UP" if sig == 1 else "DOWN",
            "exit_time": df["time"].iloc[i + hold].isoformat(),
            "exit_price": round(exit_price, 4),
            "pnl": round(pnl, 4),
            "pnl_pct": round(pnl / entry_price * 100, 4),
            "result": "WIN" if win else "LOSE",
            "reason": (
                f"{strategy['name']} 信号触发 @ "
                f"{df['time'].iloc[i].strftime('%Y-%m-%d %H:%M')}"
            ),
        })

    # 4. 汇总统计
    total = len(trades)
    wins = sum(1 for t in trades if t["result"] == "WIN")
    win_rate = wins / total if total > 0 else 0.0
    net_pnl = sum(t["pnl"] for t in trades)
    avg_win = (
        sum(t["pnl"] for t in trades if t["result"] == "WIN") / wins
        if wins > 0 else 0.0
    )
    avg_loss = (
        sum(t["pnl"] for t in trades if t["result"] == "LOSE") / (total - wins)
        if (total - wins) > 0 else 0.0
    )

    return {
        "strategy_id": strategy["id"],
        "strategy_name": strategy["name"],
        "duration": duration_min,
        "total_trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(win_rate, 4),
        "net_pnl": round(net_pnl, 4),
        "expectancy": round(net_pnl / total, 4) if total > 0 else 0.0,
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "trades": trades,
        "qualified": total >= MIN_TRADES and win_rate >= WIN_RATE_THRESHOLD,
    }


def evaluate_all(df: pd.DataFrame) -> List[Dict]:
    """
    对所有策略 × 所有时长运行回测，结果按优先级排序。
    排序规则：qualified 优先 → 胜率降序 → 期望收益降序
    """
    results = []
    for dur in CONTRACT_DURATIONS:
        for st in STRATEGIES:
            report = run_single_backtest(df, dur, st)
            results.append(report)

    results.sort(
        key=lambda x: (
            -int(x["qualified"]),
            -x["win_rate"],
            -x["expectancy"],
        )
    )
    return results


def evaluate_all_dual(df_15s: pd.DataFrame, df_1m: pd.DataFrame) -> List[Dict]:
    """
    按合约时长选 K 线粒度：3min→15s, 5min/10min→1m。
    与观测池信号粒度保持一致。
    """
    results = []
    for dur in CONTRACT_DURATIONS:
        if dur == 3 and df_15s is not None and not df_15s.empty:
            df, bar_sec = df_15s, 15
        elif df_1m is not None and not df_1m.empty:
            df, bar_sec = df_1m, 60
        else:
            df = df_15s if df_15s is not None else df_1m
            bar_sec = 15 if df is df_15s else 60
        if df is None or df.empty:
            continue
        for st in STRATEGIES:
            report = run_single_backtest(df, dur, st, bar_seconds=bar_sec)
            results.append(report)

    results.sort(key=lambda x: (-int(x["qualified"]), -x["win_rate"], -x["expectancy"]))
    return results


def get_qualified_strategies(results: List[Dict]) -> List[Dict]:
    """筛选出胜率 ≥75% 的有效策略"""
    return [r for r in results if r["qualified"]]
