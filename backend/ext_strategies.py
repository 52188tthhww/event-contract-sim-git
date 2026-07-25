"""
扩展策略 — CMF, BB%B, BB Squeeze, Pivot, Force Index, NR7
挂载到 STRATEGIES，不修改原始 strategies.py
"""
import numpy as np
import pandas as pd

# ═══════════════════════════════════════════
# CMF 蔡金资金流
# ═══════════════════════════════════════════

def cmf_signal(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    period, threshold = params["period"], params["threshold"]
    df = df.copy()
    high, low, close = df["high"], df["low"], df["close"]
    mult = ((close - low) - (high - close)) / (high - low + 1e-10)
    mf_vol = mult * df["volume"]
    df["cmf"] = mf_vol.rolling(period).sum() / (df["volume"].rolling(period).sum() + 1e-10)
    df["signal"] = np.where(df["cmf"] > threshold, 1,
                   np.where(df["cmf"] < -threshold, -1, 0))
    return df

def cmf_variants():
    return [
        {"id": "CMF_10_005", "name": "CMF 10/0.05 资金流", "fn": cmf_signal, "params": {"period": 10, "threshold": 0.05}},
        {"id": "CMF_14_005", "name": "CMF 14/0.05 资金流", "fn": cmf_signal, "params": {"period": 14, "threshold": 0.05}},
        {"id": "CMF_20_003", "name": "CMF 20/0.03 资金流", "fn": cmf_signal, "params": {"period": 20, "threshold": 0.03}},
        {"id": "CMF_7_008",  "name": "CMF 7/0.08 资金流",  "fn": cmf_signal, "params": {"period": 7, "threshold": 0.08}},
    ]

# ═══════════════════════════════════════════
# BB %B 极值反转
# ═══════════════════════════════════════════

def bb_percent_b(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    period, std_n = params["period"], params["std"]
    df = df.copy()
    ma = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    upper = ma + std_n * std
    lower = ma - std_n * std
    df["bb_b"] = (df["close"] - lower) / (upper - lower + 1e-10)
    prev_b = df["bb_b"].shift(1)
    df["signal"] = np.where(
        (prev_b < 0.1) & (df["bb_b"] > prev_b), 1,
        np.where((prev_b > 0.9) & (df["bb_b"] < prev_b), -1, 0),
    )
    return df

# ═══════════════════════════════════════════
# BB Squeeze 突破
# ═══════════════════════════════════════════

def bb_squeeze(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    period, std_n, squeeze_n = params["period"], params["std"], params["squeeze_n"]
    df = df.copy()
    ma = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    upper = ma + std_n * std
    lower = ma - std_n * std
    df["bandwidth"] = (upper - lower) / (ma + 1e-10)
    bw_min = df["bandwidth"].rolling(squeeze_n).min()
    is_squeeze = df["bandwidth"] <= bw_min
    was_squeeze = is_squeeze.shift(1)
    bw_expanding = df["bandwidth"] > df["bandwidth"].shift(1)
    df["signal"] = np.where(
        was_squeeze & bw_expanding & (df["close"] > ma), 1,
        np.where(was_squeeze & bw_expanding & (df["close"] < ma), -1, 0),
    )
    return df

# ═══════════════════════════════════════════
# Pivot Points 枢轴点
# ═══════════════════════════════════════════

def pivot_reversal(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    pivot_bars, level = params["pivot_bars"], params["level"]
    touch_pct = params.get("touch_pct", 0.3)
    df = df.copy()
    n = pivot_bars
    hh = df["high"].rolling(n).max().shift(1)
    ll = df["low"].rolling(n).min().shift(1)
    cc = df["close"].shift(1)
    pp = (hh + ll + cc) / 3
    rng = hh - ll
    r1 = 2 * pp - ll; s1 = 2 * pp - hh
    r2 = pp + rng;   s2 = pp - rng
    if level == "S1":   target = s1
    elif level == "R1": target = r1
    elif level == "S2": target = s2
    else:               target = r2

    dist_pct = (df["close"] - target) / (target + 1e-10) * 100
    touching = dist_pct.abs() < touch_pct
    if level.startswith("S"):
        df["signal"] = np.where(touching & (df["close"] > df["close"].shift(1)), 1, 0)
    else:
        df["signal"] = np.where(touching & (df["close"] < df["close"].shift(1)), -1, 0)
    return df

# ═══════════════════════════════════════════
# Force Index 力量指数
# ═══════════════════════════════════════════

def force_index_signal(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    ema_period = params["ema_period"]
    df = df.copy()
    raw_force = (df["close"] - df["close"].shift(1)) * df["volume"]
    fi_ema = raw_force.ewm(span=ema_period, adjust=False).mean()
    prev_fi = fi_ema.shift(1)
    df["signal"] = np.where(
        (prev_fi < 0) & (fi_ema > 0), 1,
        np.where((prev_fi > 0) & (fi_ema < 0), -1, 0),
    )
    return df

# ═══════════════════════════════════════════
# NR7 波动收缩
# ═══════════════════════════════════════════

def nr7_breakout(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    lookback = params["lookback"]
    df = df.copy()
    bar_range = df["high"] - df["low"]
    range_min = bar_range.rolling(lookback).min()
    is_squeeze = bar_range <= range_min
    prev_up = df["close"].shift(1) > df["open"].shift(1)
    prev_dn = df["close"].shift(1) < df["open"].shift(1)
    df["signal"] = np.where(
        is_squeeze.shift(1) & prev_up, 1,
        np.where(is_squeeze.shift(1) & prev_dn, -1, 0),
    )
    return df

# ═══════════════════════════════════════════
# 变体
# ═══════════════════════════════════════════

def bb_percent_b_variants():
    return [
        {"id": "BB_B_20_2",  "name": "BB %B 20/2 极值反转",  "fn": bb_percent_b, "params": {"period": 20, "std": 2.0}},
        {"id": "BB_B_14_2",  "name": "BB %B 14/2 极值反转",  "fn": bb_percent_b, "params": {"period": 14, "std": 2.0}},
        {"id": "BB_B_20_25", "name": "BB %B 20/2.5 极值反转", "fn": bb_percent_b, "params": {"period": 20, "std": 2.5}},
    ]

def bb_squeeze_variants():
    return [
        {"id": "BB_SQ_20_2_20",  "name": "BB Squeeze 20/2/20",  "fn": bb_squeeze, "params": {"period": 20, "std": 2.0, "squeeze_n": 20}},
        {"id": "BB_SQ_14_2_14",  "name": "BB Squeeze 14/2/14",  "fn": bb_squeeze, "params": {"period": 14, "std": 2.0, "squeeze_n": 14}},
        {"id": "BB_SQ_20_15_15", "name": "BB Squeeze 20/1.5/15", "fn": bb_squeeze, "params": {"period": 20, "std": 1.5, "squeeze_n": 15}},
    ]

def pivot_variants():
    return [
        {"id": "PIVOT_S1_1h",  "name": "Pivot S1 1h 支撑反弹",  "fn": pivot_reversal, "params": {"pivot_bars": 60, "level": "S1"}},
        {"id": "PIVOT_R1_1h",  "name": "Pivot R1 1h 阻力反转",  "fn": pivot_reversal, "params": {"pivot_bars": 60, "level": "R1"}},
        {"id": "PIVOT_S1_30m", "name": "Pivot S1 30m 支撑反弹", "fn": pivot_reversal, "params": {"pivot_bars": 30, "level": "S1"}},
        {"id": "PIVOT_R1_30m", "name": "Pivot R1 30m 阻力反转", "fn": pivot_reversal, "params": {"pivot_bars": 30, "level": "R1"}},
    ]

def force_index_variants():
    return [
        {"id": "FI_3",  "name": "ForceIndex 3 零线穿越",  "fn": force_index_signal, "params": {"ema_period": 3}},
        {"id": "FI_5",  "name": "ForceIndex 5 零线穿越",  "fn": force_index_signal, "params": {"ema_period": 5}},
        {"id": "FI_8",  "name": "ForceIndex 8 零线穿越",  "fn": force_index_signal, "params": {"ema_period": 8}},
        {"id": "FI_13", "name": "ForceIndex 13 零线穿越", "fn": force_index_signal, "params": {"ema_period": 13}},
    ]

def nr7_variants():
    return [
        {"id": "NR7_7",  "name": "NR7 波动收缩 7",  "fn": nr7_breakout, "params": {"lookback": 7}},
        {"id": "NR7_10", "name": "NR7 波动收缩 10", "fn": nr7_breakout, "params": {"lookback": 10}},
        {"id": "NR7_5",  "name": "NR7 波动收缩 5",  "fn": nr7_breakout, "params": {"lookback": 5}},
        {"id": "NR7_14", "name": "NR7 波动收缩 14", "fn": nr7_breakout, "params": {"lookback": 14}},
    ]


# 信号持续不归零的策略前缀——这类策略永远在 1 或 -1，需要限制为"翻转才开仓"
FLIP_PREFIXES = ("MA_", "EMA_", "MACD_", "ADX_", "KELT_", "MMA_", "ICHI_")


def is_flip_strategy(strategy_id: str) -> bool:
    """判断该策略是否需要翻转限制。"""
    return any(strategy_id.startswith(p) for p in FLIP_PREFIXES)


ALL_EXTENDED_VARIANTS = (
    cmf_variants() + bb_percent_b_variants() + bb_squeeze_variants() +
    pivot_variants() + force_index_variants() + nr7_variants()
)


def extend_strategies():
    """将扩展策略挂载到 STRATEGIES 列表末尾。"""
    import strategies as _st
    from combo_strategies import ALL_COMBO_VARIANTS
    existing_ids = {s["id"] for s in _st.STRATEGIES}
    for v in ALL_EXTENDED_VARIANTS + ALL_COMBO_VARIANTS:
        if v["id"] not in existing_ids:
            _st.STRATEGIES.append(v)
