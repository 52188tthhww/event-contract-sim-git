"""
新旧指标组合策略 — 多维度确认，过滤假信号
"""
import numpy as np
import pandas as pd


# ═══════════════════════════════════════════
# Pivot + RSI 共振
# ═══════════════════════════════════════════

def pivot_rsi_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Pivot S1/R1 + RSI 确认。支撑/阻力触及 + 超买超卖确认。"""
    pivot_bars, level, rsi_p, rsi_th = params["pivot_bars"], params["level"], params["rsi_period"], params["rsi_threshold"]
    df = df.copy()
    # Pivot
    n = pivot_bars
    hh = df["high"].rolling(n).max().shift(1)
    ll = df["low"].rolling(n).min().shift(1)
    cc = df["close"].shift(1)
    pp = (hh + ll + cc) / 3
    if level == "S1":  target = 2 * pp - hh
    else:              target = 2 * pp - ll
    dist_pct = (df["close"] - target) / (target + 1e-10) * 100
    near_pivot = dist_pct.abs() < params.get("touch_pct", 0.3)
    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(rsi_p).mean()
    avg_loss = loss.rolling(rsi_p).mean().replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    if level == "S1":
        df["signal"] = np.where(near_pivot & (rsi < rsi_th) & (df["close"] > df["close"].shift(1)), 1, 0)
    else:
        df["signal"] = np.where(near_pivot & (rsi > rsi_th) & (df["close"] < df["close"].shift(1)), -1, 0)
    return df


# ═══════════════════════════════════════════
# Pivot + CMF 共振
# ═══════════════════════════════════════════

def pivot_cmf_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Pivot S1 + CMF 资金流确认。支撑触及 + 资金在流入。"""
    pivot_bars, level, cmf_p = params["pivot_bars"], params["level"], params["cmf_period"]
    df = df.copy()
    # Pivot
    n = pivot_bars
    hh = df["high"].rolling(n).max().shift(1)
    ll = df["low"].rolling(n).min().shift(1)
    cc = df["close"].shift(1)
    pp = (hh + ll + cc) / 3
    if level == "S1":  target = 2 * pp - hh
    else:              target = 2 * pp - ll
    dist_pct = (df["close"] - target) / (target + 1e-10) * 100
    near_pivot = dist_pct.abs() < params.get("touch_pct", 0.3)
    # CMF
    mult = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"] + 1e-10)
    mf_vol = mult * df["volume"]
    cmf = mf_vol.rolling(cmf_p).sum() / df["volume"].rolling(cmf_p).sum()
    if level == "S1":
        df["signal"] = np.where(near_pivot & (cmf > 0) & (df["close"] > df["close"].shift(1)), 1, 0)
    else:
        df["signal"] = np.where(near_pivot & (cmf < 0) & (df["close"] < df["close"].shift(1)), -1, 0)
    return df


# ═══════════════════════════════════════════
# Force Index + 量确认
# ═══════════════════════════════════════════

def fi_volume_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Force Index 零线上穿 + 放量确认。"""
    ema_period, vol_period = params["ema_period"], params["vol_period"]
    df = df.copy()
    raw_force = (df["close"] - df["close"].shift(1)) * df["volume"]
    fi_ema = raw_force.ewm(span=ema_period, adjust=False).mean()
    prev_fi = fi_ema.shift(1)
    vol_ma = df["volume"].rolling(vol_period).mean()
    df["signal"] = np.where(
        (prev_fi < 0) & (fi_ema > 0) & (df["volume"] > vol_ma), 1,
        np.where((prev_fi > 0) & (fi_ema < 0) & (df["volume"] > vol_ma), -1, 0),
    )
    return df


# ═══════════════════════════════════════════
# NR7 + Force Index 共振
# ═══════════════════════════════════════════

def nr7_fi_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """NR7 波动收缩 + FI 零线穿越同向确认。"""
    lookback, fi_ep = params["nr7_lookback"], params["fi_ema_period"]
    df = df.copy()
    # NR7
    bar_range = df["high"] - df["low"]
    is_sq = bar_range <= bar_range.rolling(lookback).min()
    prev_up = df["close"].shift(1) > df["open"].shift(1)
    prev_dn = df["close"].shift(1) < df["open"].shift(1)
    # FI
    raw_fi = (df["close"] - df["close"].shift(1)) * df["volume"]
    fi_ema = raw_fi.ewm(span=fi_ep, adjust=False).mean()
    fi_up = (fi_ema.shift(1) < 0) & (fi_ema > 0)     # FI 零线上穿
    fi_dn = (fi_ema.shift(1) > 0) & (fi_ema < 0)     # FI 零线下穿
    df["signal"] = np.where(
        is_sq.shift(1) & prev_up & fi_up, 1,
        np.where(is_sq.shift(1) & prev_dn & fi_dn, -1, 0),
    )
    return df


# ═══════════════════════════════════════════
# CMF + RSI 共振
# ═══════════════════════════════════════════

def cmf_rsi_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """CMF 资金流方向 + RSI 超买超卖位置确认。"""
    cmf_p, rsi_p, rsi_os, rsi_ob = params["cmf_period"], params["rsi_period"], params["rsi_oversold"], params["rsi_overbought"]
    df = df.copy()
    # CMF
    mult = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"] + 1e-10)
    cmf = (mult * df["volume"]).rolling(cmf_p).sum() / df["volume"].rolling(cmf_p).sum()
    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(rsi_p).mean()
    avg_loss = loss.rolling(rsi_p).mean().replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    df["signal"] = np.where(
        (cmf > 0) & (rsi < rsi_os), 1,
        np.where((cmf < 0) & (rsi > rsi_ob), -1, 0),
    )
    return df


# ═══════════════════════════════════════════
# Pivot + 量缩 — 支撑位卖方衰竭
# ═══════════════════════════════════════════

def pivot_volume_squeeze(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Pivot S1/R1 + 成交量收缩。支撑位没人卖了/阻力位没人买了。"""
    pivot_bars, level, vol_p, vol_ratio = params["pivot_bars"], params["level"], params["vol_period"], params["vol_ratio"]
    df = df.copy()
    # Pivot
    n = pivot_bars
    hh = df["high"].rolling(n).max().shift(1)
    ll = df["low"].rolling(n).min().shift(1)
    cc = df["close"].shift(1)
    pp = (hh + ll + cc) / 3
    if level == "S1":  target = 2 * pp - hh
    else:              target = 2 * pp - ll
    dist_pct = (df["close"] - target) / (target + 1e-10) * 100
    near_pivot = dist_pct.abs() < params.get("touch_pct", 0.3)
    # 量缩：当前成交量 < 均量 * ratio（卖方衰竭）
    vol_ma = df["volume"].rolling(vol_p).mean()
    vol_dry = df["volume"] < vol_ma * vol_ratio
    # 方向确认
    if level == "S1":
        df["signal"] = np.where(near_pivot & vol_dry & (df["close"] > df["close"].shift(1)), 1, 0)
    else:
        df["signal"] = np.where(near_pivot & vol_dry & (df["close"] < df["close"].shift(1)), -1, 0)
    return df


# ═══════════════════════════════════════════
# 变体列表
# ═══════════════════════════════════════════

def pivot_rsi_variants():
    return [
        {"id": "PIVOT_S1_RSI_30", "name": "Pivot S1 30m+RSI30 共振", "fn": pivot_rsi_combo,
         "params": {"pivot_bars": 30, "level": "S1", "rsi_period": 14, "rsi_threshold": 30}},
        {"id": "PIVOT_S1_RSI_40", "name": "Pivot S1 30m+RSI40 共振", "fn": pivot_rsi_combo,
         "params": {"pivot_bars": 30, "level": "S1", "rsi_period": 14, "rsi_threshold": 40}},
        {"id": "PIVOT_R1_RSI_70", "name": "Pivot R1 30m+RSI70 共振", "fn": pivot_rsi_combo,
         "params": {"pivot_bars": 30, "level": "R1", "rsi_period": 14, "rsi_threshold": 70}},
    ]


def pivot_cmf_variants():
    return [
        {"id": "PIVOT_S1_CMF_10", "name": "Pivot S1+CMF10 共振", "fn": pivot_cmf_combo,
         "params": {"pivot_bars": 30, "level": "S1", "cmf_period": 10}},
        {"id": "PIVOT_S1_CMF_14", "name": "Pivot S1+CMF14 共振", "fn": pivot_cmf_combo,
         "params": {"pivot_bars": 30, "level": "S1", "cmf_period": 14}},
    ]


def fi_vol_variants():
    return [
        {"id": "FI_VOL_3_10", "name": "FI3+放量10 共振", "fn": fi_volume_combo,
         "params": {"ema_period": 3, "vol_period": 10}},
        {"id": "FI_VOL_5_10", "name": "FI5+放量10 共振", "fn": fi_volume_combo,
         "params": {"ema_period": 5, "vol_period": 10}},
        {"id": "FI_VOL_8_20", "name": "FI8+放量20 共振", "fn": fi_volume_combo,
         "params": {"ema_period": 8, "vol_period": 20}},
    ]


def nr7_fi_variants():
    return [
        {"id": "NR7_FI_7_5",  "name": "NR7+FI5 波动共振", "fn": nr7_fi_combo,
         "params": {"nr7_lookback": 7, "fi_ema_period": 5}},
        {"id": "NR7_FI_10_5", "name": "NR10+FI5 波动共振","fn": nr7_fi_combo,
         "params": {"nr7_lookback": 10, "fi_ema_period": 5}},
    ]


def cmf_rsi_variants():
    return [
        {"id": "CMF_RSI_10_14", "name": "CMF10+RSI14 共振", "fn": cmf_rsi_combo,
         "params": {"cmf_period": 10, "rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70}},
        {"id": "CMF_RSI_7_7",   "name": "CMF7+RSI7 共振",  "fn": cmf_rsi_combo,
         "params": {"cmf_period": 7, "rsi_period": 7, "rsi_oversold": 25, "rsi_overbought": 75}},
    ]


def pivot_vol_squeeze_variants():
    return [
        {"id": "PV_S1_30_05", "name": "Pivot S1+量缩50% 衰竭", "fn": pivot_volume_squeeze,
         "params": {"pivot_bars": 30, "level": "S1", "vol_period": 20, "vol_ratio": 0.5}},
        {"id": "PV_S1_30_07", "name": "Pivot S1+量缩70% 衰竭", "fn": pivot_volume_squeeze,
         "params": {"pivot_bars": 30, "level": "S1", "vol_period": 20, "vol_ratio": 0.7}},
        {"id": "PV_R1_30_05", "name": "Pivot R1+量缩50% 衰竭", "fn": pivot_volume_squeeze,
         "params": {"pivot_bars": 30, "level": "R1", "vol_period": 20, "vol_ratio": 0.5}},
    ]


ALL_COMBO_VARIANTS = (
    pivot_rsi_variants() + pivot_cmf_variants() +
    fi_vol_variants() + nr7_fi_variants() +
    cmf_rsi_variants() + pivot_vol_squeeze_variants()
)
