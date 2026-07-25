"""
策略库 — 每个策略输出 signal 列：1=看涨, -1=看跌, 0=无信号
"""
import numpy as np
import pandas as pd


# ═══════════════════════════════════════════
# 基础策略函数
# ═══════════════════════════════════════════

def ma_cross(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """MA 双均线交叉。快线上穿慢线→看涨，下穿→看跌。"""
    fast, slow = params["fast"], params["slow"]
    df = df.copy()
    df["ma_fast"] = df["close"].rolling(fast).mean()
    df["ma_slow"] = df["close"].rolling(slow).mean()
    df["signal"] = np.where(df["ma_fast"] > df["ma_slow"], 1,
                   np.where(df["ma_fast"] < df["ma_slow"], -1, 0))
    return df


def ema_cross(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """EMA 双均线交叉（比 MA 更灵敏）。"""
    fast, slow = params["fast"], params["slow"]
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=slow, adjust=False).mean()
    df["signal"] = np.where(df["ema_fast"] > df["ema_slow"], 1,
                   np.where(df["ema_fast"] < df["ema_slow"], -1, 0))
    return df


def macd_signal(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """MACD 柱状图穿越零轴。hist>0 且变大→看涨，hist<0 且变小→看跌。"""
    fast, slow, sig = params["fast"], params["slow"], params["signal"]
    df = df.copy()
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd"].ewm(span=sig, adjust=False).mean()
    df["hist"] = df["macd"] - df["macd_signal"]
    df["signal"] = np.where(
        (df["hist"] > 0) & (df["hist"] > df["hist"].shift(1)), 1,
        np.where((df["hist"] < 0) & (df["hist"] < df["hist"].shift(1)), -1, 0)
    )
    return df


def rsi_reversal(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """RSI 超买超卖反转。"""
    period, ob, os = params["period"], params["overbought"], params["oversold"]
    df = df.copy()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    avg_loss = avg_loss.replace(0, np.nan)
    rs = avg_gain / avg_loss
    df["rsi"] = 100.0 - (100.0 / (1.0 + rs))
    df["signal"] = np.where(df["rsi"] < os, 1,
                   np.where(df["rsi"] > ob, -1, 0))
    return df


def stochastic(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """KDJ 随机指标。K<20 超卖→看涨，K>80 超买→看跌。"""
    k_period, d_period, os, ob = params["k"], params["d"], params["oversold"], params["overbought"]
    df = df.copy()
    low_min = df["low"].rolling(k_period).min()
    high_max = df["high"].rolling(k_period).max()
    df["k"] = (df["close"] - low_min) / (high_max - low_min + 1e-10) * 100
    df["d"] = df["k"].rolling(d_period).mean()
    df["signal"] = np.where(df["k"] < os, 1,
                   np.where(df["k"] > ob, -1, 0))
    return df


def cci_channel(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """CCI 商品通道指数。CCI<-100 超卖→看涨，CCI>100 超买→看跌。"""
    period, upper, lower = params["period"], params["upper"], params["lower"]
    df = df.copy()
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean())
    df["cci"] = (tp - ma) / (0.015 * mad + 1e-10)
    df["signal"] = np.where(df["cci"] < lower, 1,
                   np.where(df["cci"] > upper, -1, 0))
    return df


def bb_breakout(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """布林带突破。"""
    period, std_n = params["period"], params["std"]
    df = df.copy()
    ma = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    df["signal"] = np.where(df["close"] > ma + std_n * std, 1,
                   np.where(df["close"] < ma - std_n * std, -1, 0))
    return df


def donchian_breakout(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """唐奇安通道突破。价格突破N周期高点→看涨，跌破N周期低点→看跌。"""
    period = params["period"]
    df = df.copy()
    upper = df["high"].rolling(period).max().shift(1)
    lower = df["low"].rolling(period).min().shift(1)
    df["signal"] = np.where(df["close"] > upper, 1,
                   np.where(df["close"] < lower, -1, 0))
    return df


def atr_volatility(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """ATR 波动率突破。价格涨跌幅超过 N×ATR → 顺势开仓。"""
    period, mult = params["period"], params["mult"]
    df = df.copy()
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(period).mean()
    change = df["close"].diff()
    df["signal"] = np.where(change > mult * df["atr"], 1,
                   np.where(change < -mult * df["atr"], -1, 0))
    return df


def volume_surge(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """成交量突增 + 价格方向。量>N倍均量 且 涨→看涨，量>N倍均量 且 跌→看跌。"""
    period, vol_mult = params["period"], params["vol_mult"]
    df = df.copy()
    df["vol_ma"] = df["volume"].rolling(period).mean()
    df["price_chg"] = df["close"].diff()
    df["signal"] = np.where(
        (df["volume"] > vol_mult * df["vol_ma"]) & (df["price_chg"] > 0), 1,
        np.where((df["volume"] > vol_mult * df["vol_ma"]) & (df["price_chg"] < 0), -1, 0)
    )
    return df


def momentum_breakout(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """动量突破。N根K线涨跌幅超过阈值→顺势。"""
    period, threshold = params["period"], params["threshold"]
    df = df.copy()
    df["roc"] = df["close"].pct_change(period) * 100
    df["signal"] = np.where(df["roc"] > threshold, 1,
                   np.where(df["roc"] < -threshold, -1, 0))
    return df


# ═══════════════════════════════════════════
# 策略组合生成
# ═══════════════════════════════════════════

def ma_variants():
    return [
        {"id": "MA_3_10",  "name": "MA 3/10 趋势跟踪",   "fn": ma_cross, "params": {"fast": 3, "slow": 10}},
        {"id": "MA_5_10",  "name": "MA 5/10 趋势跟踪",   "fn": ma_cross, "params": {"fast": 5, "slow": 10}},
        {"id": "MA_5_20",  "name": "MA 5/20 趋势跟踪",   "fn": ma_cross, "params": {"fast": 5, "slow": 20}},
        {"id": "MA_5_30",  "name": "MA 5/30 趋势跟踪",   "fn": ma_cross, "params": {"fast": 5, "slow": 30}},
        {"id": "MA_10_20", "name": "MA 10/20 趋势跟踪",  "fn": ma_cross, "params": {"fast": 10, "slow": 20}},
        {"id": "MA_10_30", "name": "MA 10/30 趋势跟踪",  "fn": ma_cross, "params": {"fast": 10, "slow": 30}},
        {"id": "MA_10_50", "name": "MA 10/50 趋势跟踪",  "fn": ma_cross, "params": {"fast": 10, "slow": 50}},
        {"id": "MA_20_50", "name": "MA 20/50 趋势跟踪",  "fn": ma_cross, "params": {"fast": 20, "slow": 50}},
    ]


def ema_variants():
    return [
        {"id": "EMA_3_10",  "name": "EMA 3/10 趋势跟踪",  "fn": ema_cross, "params": {"fast": 3, "slow": 10}},
        {"id": "EMA_5_13",  "name": "EMA 5/13 趋势跟踪",  "fn": ema_cross, "params": {"fast": 5, "slow": 13}},
        {"id": "EMA_8_21",  "name": "EMA 8/21 趋势跟踪",  "fn": ema_cross, "params": {"fast": 8, "slow": 21}},
        {"id": "EMA_12_26", "name": "EMA 12/26 趋势跟踪", "fn": ema_cross, "params": {"fast": 12, "slow": 26}},
        {"id": "EMA_5_20",  "name": "EMA 5/20 趋势跟踪",  "fn": ema_cross, "params": {"fast": 5, "slow": 20}},
        {"id": "EMA_5_34",  "name": "EMA 5/34 趋势跟踪",  "fn": ema_cross, "params": {"fast": 5, "slow": 34}},
    ]


def macd_variants():
    return [
        {"id": "MACD_12_26_9",  "name": "MACD 12/26/9 柱状图",  "fn": macd_signal, "params": {"fast": 12, "slow": 26, "signal": 9}},
        {"id": "MACD_8_17_9",   "name": "MACD 8/17/9 柱状图",   "fn": macd_signal, "params": {"fast": 8, "slow": 17, "signal": 9}},
        {"id": "MACD_5_13_5",   "name": "MACD 5/13/5 柱状图",   "fn": macd_signal, "params": {"fast": 5, "slow": 13, "signal": 5}},
        {"id": "MACD_3_10_3",   "name": "MACD 3/10/3 柱状图",   "fn": macd_signal, "params": {"fast": 3, "slow": 10, "signal": 3}},
    ]


def rsi_variants():
    return [
        {"id": "RSI_7_80_20",  "name": "RSI 7 反转 (20/80)",   "fn": rsi_reversal, "params": {"period": 7, "overbought": 80, "oversold": 20}},
        {"id": "RSI_9_75_25",  "name": "RSI 9 反转 (25/75)",   "fn": rsi_reversal, "params": {"period": 9, "overbought": 75, "oversold": 25}},
        {"id": "RSI_14_70_30", "name": "RSI 14 反转 (30/70)",  "fn": rsi_reversal, "params": {"period": 14, "overbought": 70, "oversold": 30}},
        {"id": "RSI_14_75_25", "name": "RSI 14 反转 (25/75)",  "fn": rsi_reversal, "params": {"period": 14, "overbought": 75, "oversold": 25}},
        {"id": "RSI_21_70_30", "name": "RSI 21 反转 (30/70)",  "fn": rsi_reversal, "params": {"period": 21, "overbought": 70, "oversold": 30}},
        {"id": "RSI_21_65_35", "name": "RSI 21 反转 (35/65)",  "fn": rsi_reversal, "params": {"period": 21, "overbought": 65, "oversold": 35}},
    ]


def stochastic_variants():
    return [
        {"id": "KDJ_9_3_20_80",   "name": "KDJ 9/3 (20/80)",   "fn": stochastic, "params": {"k": 9, "d": 3, "oversold": 20, "overbought": 80}},
        {"id": "KDJ_14_3_20_80",  "name": "KDJ 14/3 (20/80)",  "fn": stochastic, "params": {"k": 14, "d": 3, "oversold": 20, "overbought": 80}},
        {"id": "KDJ_5_3_25_75",   "name": "KDJ 5/3 (25/75)",   "fn": stochastic, "params": {"k": 5, "d": 3, "oversold": 25, "overbought": 75}},
        {"id": "KDJ_21_5_15_85",  "name": "KDJ 21/5 (15/85)",  "fn": stochastic, "params": {"k": 21, "d": 5, "oversold": 15, "overbought": 85}},
    ]


def cci_variants():
    return [
        {"id": "CCI_14_100",  "name": "CCI 14 (±100)",  "fn": cci_channel, "params": {"period": 14, "upper": 100, "lower": -100}},
        {"id": "CCI_20_100",  "name": "CCI 20 (±100)",  "fn": cci_channel, "params": {"period": 20, "upper": 100, "lower": -100}},
        {"id": "CCI_14_150",  "name": "CCI 14 (±150)",  "fn": cci_channel, "params": {"period": 14, "upper": 150, "lower": -150}},
        {"id": "CCI_7_80",    "name": "CCI 7 (±80)",    "fn": cci_channel, "params": {"period": 7, "upper": 80, "lower": -80}},
    ]


def bb_variants():
    return [
        {"id": "BB_10_15",  "name": "布林带 10/1.5 突破", "fn": bb_breakout, "params": {"period": 10, "std": 1.5}},
        {"id": "BB_14_20",  "name": "布林带 14/2.0 突破", "fn": bb_breakout, "params": {"period": 14, "std": 2.0}},
        {"id": "BB_20_20",  "name": "布林带 20/2.0 突破", "fn": bb_breakout, "params": {"period": 20, "std": 2.0}},
        {"id": "BB_20_25",  "name": "布林带 20/2.5 突破", "fn": bb_breakout, "params": {"period": 20, "std": 2.5}},
        {"id": "BB_30_20",  "name": "布林带 30/2.0 突破", "fn": bb_breakout, "params": {"period": 30, "std": 2.0}},
    ]


def donchian_variants():
    return [
        {"id": "DC_10", "name": "唐奇安 10 突破", "fn": donchian_breakout, "params": {"period": 10}},
        {"id": "DC_20", "name": "唐奇安 20 突破", "fn": donchian_breakout, "params": {"period": 20}},
        {"id": "DC_30", "name": "唐奇安 30 突破", "fn": donchian_breakout, "params": {"period": 30}},
        {"id": "DC_5",  "name": "唐奇安 5 突破",  "fn": donchian_breakout, "params": {"period": 5}},
    ]


def atr_variants():
    return [
        {"id": "ATR_14_05", "name": "ATR 14/0.5 波动突破", "fn": atr_volatility, "params": {"period": 14, "mult": 0.5}},
        {"id": "ATR_14_10", "name": "ATR 14/1.0 波动突破", "fn": atr_volatility, "params": {"period": 14, "mult": 1.0}},
        {"id": "ATR_14_15", "name": "ATR 14/1.5 波动突破", "fn": atr_volatility, "params": {"period": 14, "mult": 1.5}},
        {"id": "ATR_7_10",  "name": "ATR 7/1.0 波动突破",  "fn": atr_volatility, "params": {"period": 7, "mult": 1.0}},
    ]


def volume_variants():
    return [
        {"id": "VOL_20_15", "name": "量能 20/1.5x 突增", "fn": volume_surge, "params": {"period": 20, "vol_mult": 1.5}},
        {"id": "VOL_20_20", "name": "量能 20/2.0x 突增", "fn": volume_surge, "params": {"period": 20, "vol_mult": 2.0}},
        {"id": "VOL_10_15", "name": "量能 10/1.5x 突增", "fn": volume_surge, "params": {"period": 10, "vol_mult": 1.5}},
        {"id": "VOL_30_20", "name": "量能 30/2.0x 突增", "fn": volume_surge, "params": {"period": 30, "vol_mult": 2.0}},
    ]


def momentum_variants():
    return [
        {"id": "MOM_3_05", "name": "动量 3K/0.5% 突破", "fn": momentum_breakout, "params": {"period": 3, "threshold": 0.5}},
        {"id": "MOM_5_05", "name": "动量 5K/0.5% 突破", "fn": momentum_breakout, "params": {"period": 5, "threshold": 0.5}},
        {"id": "MOM_5_10", "name": "动量 5K/1.0% 突破", "fn": momentum_breakout, "params": {"period": 5, "threshold": 1.0}},
        {"id": "MOM_10_10","name": "动量 10K/1.0% 突破","fn": momentum_breakout, "params": {"period": 10, "threshold": 1.0}},
    ]


# ═══════════════════════════════════════════
# ADX / Supertrend / MFI / Ichimoku / Keltner
# ═══════════════════════════════════════════

def adx_trend(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """ADX 趋势强度。ADX>25且+DI>-DI→看涨，ADX>25且+DI<-DI→看跌。"""
    period = params["period"]
    df = df.copy()
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    df["adx"] = dx.rolling(period).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    df["signal"] = np.where(
        (df["adx"] > 25) & (df["plus_di"] > df["minus_di"]), 1,
        np.where((df["adx"] > 25) & (df["minus_di"] > df["plus_di"]), -1, 0),
    )
    return df


def supertrend(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Supertrend 超级趋势。价格>上轨→看涨，价格<下轨→看跌。"""
    period, mult = params["period"], params["mult"]
    df = df.copy()
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    hl2 = (high + low) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    trend = [1] * len(df)
    for i in range(1, len(df)):
        if close.iloc[i] > upper.iloc[i-1]:
            trend[i] = 1
        elif close.iloc[i] < lower.iloc[i-1]:
            trend[i] = -1
        else:
            trend[i] = trend[i-1]
            upper.iloc[i] = min(upper.iloc[i], upper.iloc[i-1]) if trend[i] == 1 else upper.iloc[i]
            lower.iloc[i] = max(lower.iloc[i], lower.iloc[i-1]) if trend[i] == -1 else lower.iloc[i]
    df["signal"] = np.where(
        (np.array(trend) == 1) & (np.array(trend) != np.roll(np.array(trend), 1)), 1,
        np.where((np.array(trend) == -1) & (np.array(trend) != np.roll(np.array(trend), 1)), -1, 0),
    )
    return df


def mfi_reversal(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """MFI 资金流量指数。MFI<20超卖→看涨，MFI>80超买→看跌。"""
    period, ob, os = params["period"], params["overbought"], params["oversold"]
    df = df.copy()
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]
    pos_flow = mf.where(tp > tp.shift(1), 0.0)
    neg_flow = mf.where(tp < tp.shift(1), 0.0)
    pos_sum = pos_flow.rolling(period).sum()
    neg_sum = neg_flow.rolling(period).sum()
    mr = pos_sum / (neg_sum + 1e-10)
    df["mfi"] = 100 - (100 / (1 + mr))
    df["signal"] = np.where(df["mfi"] < os, 1, np.where(df["mfi"] > ob, -1, 0))
    return df


def ichimoku(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Ichimoku 一目均衡。价格>云层且转换线>基准线→看涨，反之看跌。"""
    t, k, s = params["tenkan"], params["kijun"], params["senkou_b"]
    df = df.copy()
    high, low = df["high"], df["low"]
    df["tenkan"] = (high.rolling(t).max() + low.rolling(t).min()) / 2
    df["kijun"] = (high.rolling(k).max() + low.rolling(k).min()) / 2
    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(k)
    df["senkou_b"] = ((high.rolling(s).max() + low.rolling(s).min()) / 2).shift(k)
    df["signal"] = np.where(
        (df["close"] > df["senkou_a"]) & (df["close"] > df["senkou_b"]) & (df["tenkan"] > df["kijun"]), 1,
        np.where((df["close"] < df["senkou_a"]) & (df["close"] < df["senkou_b"]) & (df["tenkan"] < df["kijun"]), -1, 0),
    )
    return df


def keltner_breakout(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Keltner 通道突破。价格>上轨→看涨，价格<下轨→看跌。"""
    period, atr_p, mult = params["ema_period"], params["atr_period"], params["mult"]
    df = df.copy()
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(atr_p).mean()
    ema = close.ewm(span=period, adjust=False).mean()
    upper = ema + mult * atr
    lower = ema - mult * atr
    df["signal"] = np.where(close > upper, 1, np.where(close < lower, -1, 0))
    return df


# ═══════════════════════════════════════════
# OBV / 情绪 / 复合
# ═══════════════════════════════════════════

def obv_divergence(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """OBV 能量潮：价格涨+量，价格跌-量。OBV创新高且价未新高→看跌(背离)，OBV创新低且价未新低→看涨(背离)。"""
    period = params["period"]
    df = df.copy()
    df["price_chg"] = df["close"].diff()
    df["obv"] = (df["volume"] * np.where(df["close"] > df["close"].shift(1), 1,
                                 np.where(df["close"] < df["close"].shift(1), -1, 0))).cumsum()
    df["obv_high"] = df["obv"].rolling(period).max()
    df["obv_low"] = df["obv"].rolling(period).min()
    df["price_high"] = df["close"].rolling(period).max()
    df["price_low"] = df["close"].rolling(period).min()
    # OBV顶背离: OBV未创新高但价格创新高→看跌
    # OBV底背离: OBV未创新低但价格创新低→看涨
    df["signal"] = np.where(
        (df["close"] <= df["price_low"]) & (df["obv"] > df["obv_low"].shift(1)), 1,
        np.where((df["close"] >= df["price_high"]) & (df["obv"] < df["obv_high"].shift(1)), -1, 0),
    )
    return df


# ═══════════════════════════════════════════
# 合约市场情绪策略（资金费率 / 多空比 / 持仓量）
# 注意：这些策略依赖外部数据，回测时使用历史K线数据模拟
# ═══════════════════════════════════════════

def funding_sentiment(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    资金费率极端值反转：费率极高(多头拥挤)→看跌，费率极低(空头拥挤)→看涨。
    回测中用价格波动率近似模拟费率极端场景。
    """
    period, threshold = params["period"], params["threshold"]
    df = df.copy()
    # 用近期价格涨跌幅近似模拟资金费率方向
    df["price_roc"] = df["close"].pct_change(period) * 100
    # 涨幅过大=多头拥挤=看跌，跌幅过大=空头拥挤=看涨
    df["signal"] = np.where(df["price_roc"] > threshold, -1,
                   np.where(df["price_roc"] < -threshold, 1, 0))
    return df


def open_interest_breakout(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    持仓量变化+价格方向：量价齐升→看涨(趋势确认)，量价背离→看跌。
    """
    period = params["period"]
    df = df.copy()
    # 用成交量变化近似模拟持仓量变化
    df["vol_chg"] = df["volume"].pct_change(period)
    df["price_chg"] = df["close"].pct_change(period)
    df["signal"] = np.where(
        (df["vol_chg"] > 0.1) & (df["price_chg"] > 0), 1,
        np.where((df["vol_chg"] > 0.1) & (df["price_chg"] < 0), -1, 0),
    )
    return df


# ═══════════════════════════════════════════
# 三重确认复合策略
# ═══════════════════════════════════════════

def triple_confirm(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """三重确认：趋势(MA金叉)+震荡(RSI<50)+量能(放量) → 同向才开仓"""
    ma_f, ma_s, rsi_p, vol_p = params["ma_fast"], params["ma_slow"], params["rsi_period"], params["vol_period"]
    df = df.copy()
    df["ma_f"] = df["close"].rolling(ma_f).mean()
    df["ma_s"] = df["close"].rolling(ma_s).mean()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(rsi_p).mean()
    avg_loss = loss.rolling(rsi_p).mean().replace(0, np.nan)
    df["rsi"] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    df["vol_ma"] = df["volume"].rolling(vol_p).mean()
    df["signal"] = np.where(
        (df["ma_f"] > df["ma_s"]) & (df["rsi"] < 50) & (df["volume"] > df["vol_ma"]), 1,
        np.where((df["ma_f"] < df["ma_s"]) & (df["rsi"] > 50) & (df["volume"] > df["vol_ma"]), -1, 0),
    )
    return df


def bb_macd_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """布林带+MACD双重确认"""
    bb_p, bb_std, macd_f, macd_s, macd_sig = params["bb_period"], params["bb_std"], params["macd_fast"], params["macd_slow"], params["macd_signal"]
    df = df.copy()
    # BB
    ma = df["close"].rolling(bb_p).mean()
    std = df["close"].rolling(bb_p).std()
    df["bb_upper"] = ma + bb_std * std
    df["bb_lower"] = ma - bb_std * std
    # MACD
    ema_f = df["close"].ewm(span=macd_f, adjust=False).mean()
    ema_s = df["close"].ewm(span=macd_s, adjust=False).mean()
    df["macd"] = ema_f - ema_s
    df["macd_sig"] = df["macd"].ewm(span=macd_sig, adjust=False).mean()
    df["hist"] = df["macd"] - df["macd_sig"]
    # 布林下轨+MACD金叉→看涨，布林上轨+MACD死叉→看跌
    df["signal"] = np.where(
        (df["close"] < df["bb_lower"]) & (df["hist"] > 0), 1,
        np.where((df["close"] > df["bb_upper"]) & (df["hist"] < 0), -1, 0),
    )
    return df


def rsi_volume_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """RSI超卖/超买+成交量确认"""
    rsi_p, ob, os, vol_p = params["rsi_period"], params["overbought"], params["oversold"], params["vol_period"]
    df = df.copy()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(rsi_p).mean()
    avg_loss = loss.rolling(rsi_p).mean().replace(0, np.nan)
    df["rsi"] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    df["vol_ma"] = df["volume"].rolling(vol_p).mean()
    df["signal"] = np.where(
        (df["rsi"] < os) & (df["volume"] > df["vol_ma"]), 1,
        np.where((df["rsi"] > ob) & (df["volume"] > df["vol_ma"]), -1, 0),
    )
    return df


def kdj_macd_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """KDJ超卖/超买+MACD确认"""
    k_p, d_p, os, ob, m_f, m_s, m_sig = params["k_period"], params["d_period"], params["oversold"], params["overbought"], params["macd_fast"], params["macd_slow"], params["macd_signal"]
    df = df.copy()
    # KDJ
    low_min = df["low"].rolling(k_p).min()
    high_max = df["high"].rolling(k_p).max()
    df["k"] = (df["close"] - low_min) / (high_max - low_min + 1e-10) * 100
    df["d"] = df["k"].rolling(d_p).mean()
    # MACD
    ema_f = df["close"].ewm(span=m_f, adjust=False).mean()
    ema_s = df["close"].ewm(span=m_s, adjust=False).mean()
    df["macd"] = ema_f - ema_s
    df["macd_sig"] = df["macd"].ewm(span=m_sig, adjust=False).mean()
    df["signal"] = np.where(
        (df["k"] < os) & (df["macd"] > df["macd_sig"]), 1,
        np.where((df["k"] > ob) & (df["macd"] < df["macd_sig"]), -1, 0),
    )
    return df


# ═══════════════════════════════════════════
# 复合策略
# ═══════════════════════════════════════════

def ema_rsi_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """EMA趋势 + RSI确认：EMA金叉且RSI<50→看涨，EMA死叉且RSI>50→看跌"""
    fast, slow, rsi_period = params["fast"], params["slow"], params["rsi_period"]
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=slow, adjust=False).mean()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(rsi_period).mean()
    avg_loss = loss.rolling(rsi_period).mean().replace(0, np.nan)
    df["rsi"] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    df["signal"] = np.where(
        (df["ema_fast"] > df["ema_slow"]) & (df["rsi"] < 50), 1,
        np.where((df["ema_fast"] < df["ema_slow"]) & (df["rsi"] > 50), -1, 0),
    )
    return df


def bb_rsi_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """布林带+RSI：价格破下轨且RSI<30→看涨，价格破上轨且RSI>70→看跌"""
    period, std_n, rsi_p = params["period"], params["std"], params["rsi_period"]
    df = df.copy()
    ma = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    df["bb_lower"] = ma - std_n * std
    df["bb_upper"] = ma + std_n * std
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(rsi_p).mean()
    avg_loss = loss.rolling(rsi_p).mean().replace(0, np.nan)
    rs = avg_gain / avg_loss
    df["rsi"] = 100.0 - (100.0 / (1.0 + rs))
    df["signal"] = np.where(
        (df["close"] < df["bb_lower"]) & (df["rsi"] < 30), 1,
        np.where((df["close"] > df["bb_upper"]) & (df["rsi"] > 70), -1, 0),
    )
    return df


def ma_volume_combo(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """MA趋势+量确认：MA金叉且放量→看涨，MA死叉且放量→看跌"""
    fast, slow, vol_p = params["fast"], params["slow"], params["vol_period"]
    df = df.copy()
    df["ma_fast"] = df["close"].rolling(fast).mean()
    df["ma_slow"] = df["close"].rolling(slow).mean()
    df["vol_ma"] = df["volume"].rolling(vol_p).mean()
    df["signal"] = np.where(
        (df["ma_fast"] > df["ma_slow"]) & (df["volume"] > df["vol_ma"]), 1,
        np.where((df["ma_fast"] < df["ma_slow"]) & (df["volume"] > df["vol_ma"]), -1, 0),
    )
    return df


def psar_signal(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Parabolic SAR 方向：SAR<价格→看涨，SAR>价格→看跌"""
    af_start, af_step, af_max = params["af_start"], params["af_step"], params["af_max"]
    df = df.copy()
    n = len(df)
    sar = [0.0] * n
    trend = [1] * n
    ep = [0.0] * n
    af = [af_start] * n
    # 初始化
    trend[0] = 1
    sar[0] = df["low"].iloc[0]
    ep[0] = df["high"].iloc[0]
    for i in range(1, n):
        sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
        if trend[i-1] == 1:
            sar[i] = min(sar[i], df["low"].iloc[i-1], df["low"].iloc[max(i-2,0)])
            if df["low"].iloc[i] < sar[i]:
                trend[i] = -1
                sar[i] = ep[i-1]
                ep[i] = df["low"].iloc[i]
                af[i] = af_start
            else:
                trend[i] = 1
                if df["high"].iloc[i] > ep[i-1]:
                    ep[i] = df["high"].iloc[i]
                    af[i] = min(af[i-1] + af_step, af_max)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
        else:
            sar[i] = max(sar[i], df["high"].iloc[i-1], df["high"].iloc[max(i-2,0)])
            if df["high"].iloc[i] > sar[i]:
                trend[i] = 1
                sar[i] = ep[i-1]
                ep[i] = df["high"].iloc[i]
                af[i] = af_start
            else:
                trend[i] = -1
                if df["low"].iloc[i] < ep[i-1]:
                    ep[i] = df["low"].iloc[i]
                    af[i] = min(af[i-1] + af_step, af_max)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
    df["signal"] = np.where(
        (np.array(trend) == 1) & (np.array(trend) != np.roll(trend, 1)), 1,
        np.where((np.array(trend) == -1) & (np.array(trend) != np.roll(trend, 1)), -1, 0),
    )
    return df


def multi_ma_trend(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """多周期MA排列：短>中>长→看涨，短<中<长→看跌"""
    s, m, l = params["short"], params["med"], params["long"]
    df = df.copy()
    df["ma_s"] = df["close"].rolling(s).mean()
    df["ma_m"] = df["close"].rolling(m).mean()
    df["ma_l"] = df["close"].rolling(l).mean()
    df["signal"] = np.where(
        (df["ma_s"] > df["ma_m"]) & (df["ma_m"] > df["ma_l"]), 1,
        np.where((df["ma_s"] < df["ma_m"]) & (df["ma_m"] < df["ma_l"]), -1, 0),
    )
    return df


# ═══════════════════════════════════════════
# 扩展变体生成
# ═══════════════════════════════════════════

def ema_rsi_variants():
    return [
        {"id": "EMA_RSI_5_20_14", "name": "EMA5/20+RSI14 共振", "fn": ema_rsi_combo, "params": {"fast": 5, "slow": 20, "rsi_period": 14}},
        {"id": "EMA_RSI_8_21_14", "name": "EMA8/21+RSI14 共振", "fn": ema_rsi_combo, "params": {"fast": 8, "slow": 21, "rsi_period": 14}},
        {"id": "EMA_RSI_3_10_7",  "name": "EMA3/10+RSI7 共振",  "fn": ema_rsi_combo, "params": {"fast": 3, "slow": 10, "rsi_period": 7}},
        {"id": "EMA_RSI_12_26_14","name": "EMA12/26+RSI14 共振", "fn": ema_rsi_combo, "params": {"fast": 12, "slow": 26, "rsi_period": 14}},
    ]


def bb_rsi_variants():
    return [
        {"id": "BB_RSI_20_2_14",  "name": "BB20/2+RSI14 共振", "fn": bb_rsi_combo, "params": {"period": 20, "std": 2.0, "rsi_period": 14}},
        {"id": "BB_RSI_14_2_14",  "name": "BB14/2+RSI14 共振", "fn": bb_rsi_combo, "params": {"period": 14, "std": 2.0, "rsi_period": 14}},
        {"id": "BB_RSI_20_25_7",  "name": "BB20/2.5+RSI7 共振","fn": bb_rsi_combo, "params": {"period": 20, "std": 2.5, "rsi_period": 7}},
    ]


def ma_vol_variants():
    return [
        {"id": "MA_VOL_5_20_20",  "name": "MA5/20+量 共振", "fn": ma_volume_combo, "params": {"fast": 5, "slow": 20, "vol_period": 20}},
        {"id": "MA_VOL_10_30_20", "name": "MA10/30+量 共振","fn": ma_volume_combo, "params": {"fast": 10, "slow": 30, "vol_period": 20}},
        {"id": "MA_VOL_3_10_10",  "name": "MA3/10+量 共振", "fn": ma_volume_combo, "params": {"fast": 3, "slow": 10, "vol_period": 10}},
    ]


def psar_variants():
    return [
        {"id": "PSAR_002_002_02", "name": "PSAR 0.02/0.2", "fn": psar_signal, "params": {"af_start": 0.02, "af_step": 0.02, "af_max": 0.2}},
        {"id": "PSAR_001_001_01", "name": "PSAR 0.01/0.1", "fn": psar_signal, "params": {"af_start": 0.01, "af_step": 0.01, "af_max": 0.1}},
        {"id": "PSAR_003_003_03", "name": "PSAR 0.03/0.3", "fn": psar_signal, "params": {"af_start": 0.03, "af_step": 0.03, "af_max": 0.3}},
    ]


def multi_ma_variants():
    return [
        {"id": "MMA_3_10_20",  "name": "多MA 3/10/20 排列", "fn": multi_ma_trend, "params": {"short": 3, "med": 10, "long": 20}},
        {"id": "MMA_5_20_50",  "name": "多MA 5/20/50 排列", "fn": multi_ma_trend, "params": {"short": 5, "med": 20, "long": 50}},
        {"id": "MMA_10_30_60", "name": "多MA 10/30/60 排列","fn": multi_ma_trend, "params": {"short": 10, "med": 30, "long": 60}},
    ]


def extended_ma_variants():
    return [
        {"id": "MA_3_15",  "name": "MA 3/15 趋势跟踪",  "fn": ma_cross, "params": {"fast": 3, "slow": 15}},
        {"id": "MA_7_21",  "name": "MA 7/21 趋势跟踪",  "fn": ma_cross, "params": {"fast": 7, "slow": 21}},
        {"id": "MA_15_60", "name": "MA 15/60 趋势跟踪", "fn": ma_cross, "params": {"fast": 15, "slow": 60}},
        {"id": "MA_30_90", "name": "MA 30/90 趋势跟踪", "fn": ma_cross, "params": {"fast": 30, "slow": 90}},
    ]


def extended_ema_variants():
    return [
        {"id": "EMA_3_15",  "name": "EMA 3/15 趋势跟踪",  "fn": ema_cross, "params": {"fast": 3, "slow": 15}},
        {"id": "EMA_7_21",  "name": "EMA 7/21 趋势跟踪",  "fn": ema_cross, "params": {"fast": 7, "slow": 21}},
        {"id": "EMA_10_40", "name": "EMA 10/40 趋势跟踪", "fn": ema_cross, "params": {"fast": 10, "slow": 40}},
        {"id": "EMA_15_60", "name": "EMA 15/60 趋势跟踪", "fn": ema_cross, "params": {"fast": 15, "slow": 60}},
    ]


def extended_rsi_variants():
    return [
        {"id": "RSI_5_85_15",  "name": "RSI 5 反转 (15/85)",  "fn": rsi_reversal, "params": {"period": 5, "overbought": 85, "oversold": 15}},
        {"id": "RSI_10_80_20", "name": "RSI 10 反转 (20/80)", "fn": rsi_reversal, "params": {"period": 10, "overbought": 80, "oversold": 20}},
        {"id": "RSI_10_70_30", "name": "RSI 10 反转 (30/70)", "fn": rsi_reversal, "params": {"period": 10, "overbought": 70, "oversold": 30}},
        {"id": "RSI_28_70_30", "name": "RSI 28 反转 (30/70)", "fn": rsi_reversal, "params": {"period": 28, "overbought": 70, "oversold": 30}},
    ]


def extended_bb_variants():
    return [
        {"id": "BB_15_15", "name": "布林带 15/1.5 突破", "fn": bb_breakout, "params": {"period": 15, "std": 1.5}},
        {"id": "BB_15_25", "name": "布林带 15/2.5 突破", "fn": bb_breakout, "params": {"period": 15, "std": 2.5}},
        {"id": "BB_10_10", "name": "布林带 10/1.0 突破", "fn": bb_breakout, "params": {"period": 10, "std": 1.0}},
        {"id": "BB_25_20", "name": "布林带 25/2.0 突破", "fn": bb_breakout, "params": {"period": 25, "std": 2.0}},
    ]


def extended_stoch_variants():
    return [
        {"id": "KDJ_7_3_20_80",  "name": "KDJ 7/3 (20/80)",  "fn": stochastic, "params": {"k": 7, "d": 3, "oversold": 20, "overbought": 80}},
        {"id": "KDJ_10_5_30_70", "name": "KDJ 10/5 (30/70)", "fn": stochastic, "params": {"k": 10, "d": 5, "oversold": 30, "overbought": 70}},
        {"id": "KDJ_28_5_20_80", "name": "KDJ 28/5 (20/80)", "fn": stochastic, "params": {"k": 28, "d": 5, "oversold": 20, "overbought": 80}},
    ]


def extended_cci_variants():
    return [
        {"id": "CCI_10_120", "name": "CCI 10 (±120)", "fn": cci_channel, "params": {"period": 10, "upper": 120, "lower": -120}},
        {"id": "CCI_30_100", "name": "CCI 30 (±100)", "fn": cci_channel, "params": {"period": 30, "upper": 100, "lower": -100}},
        {"id": "CCI_20_150", "name": "CCI 20 (±150)", "fn": cci_channel, "params": {"period": 20, "upper": 150, "lower": -150}},
    ]


def extended_momentum_variants():
    return [
        {"id": "MOM_3_10",  "name": "动量 3K/1.0% 突破",  "fn": momentum_breakout, "params": {"period": 3, "threshold": 1.0}},
        {"id": "MOM_7_10",  "name": "动量 7K/1.0% 突破",  "fn": momentum_breakout, "params": {"period": 7, "threshold": 1.0}},
        {"id": "MOM_10_15", "name": "动量 10K/1.5% 突破", "fn": momentum_breakout, "params": {"period": 10, "threshold": 1.5}},
        {"id": "MOM_3_03",  "name": "动量 3K/0.3% 突破",  "fn": momentum_breakout, "params": {"period": 3, "threshold": 0.3}},
    ]


def extended_atr_variants():
    return [
        {"id": "ATR_10_08", "name": "ATR 10/0.8 波动突破",  "fn": atr_volatility, "params": {"period": 10, "mult": 0.8}},
        {"id": "ATR_20_10", "name": "ATR 20/1.0 波动突破",  "fn": atr_volatility, "params": {"period": 20, "mult": 1.0}},
        {"id": "ATR_14_20", "name": "ATR 14/2.0 波动突破",  "fn": atr_volatility, "params": {"period": 14, "mult": 2.0}},
    ]


def extended_volume_variants():
    return [
        {"id": "VOL_15_18", "name": "量能 15/1.8x 突增", "fn": volume_surge, "params": {"period": 15, "vol_mult": 1.8}},
        {"id": "VOL_20_25", "name": "量能 20/2.5x 突增", "fn": volume_surge, "params": {"period": 20, "vol_mult": 2.5}},
        {"id": "VOL_5_12",  "name": "量能 5/1.2x 突增",  "fn": volume_surge, "params": {"period": 5, "vol_mult": 1.2}},
    ]


def obv_variants():
    return [
        {"id": "OBV_10", "name": "OBV 10 背离", "fn": obv_divergence, "params": {"period": 10}},
        {"id": "OBV_14", "name": "OBV 14 背离", "fn": obv_divergence, "params": {"period": 14}},
        {"id": "OBV_20", "name": "OBV 20 背离", "fn": obv_divergence, "params": {"period": 20}},
    ]

def funding_variants():
    return [
        {"id": "FUNDING_10_3",  "name": "费率反转 10/3%", "fn": funding_sentiment, "params": {"period": 10, "threshold": 3.0}},
        {"id": "FUNDING_14_2",  "name": "费率反转 14/2%", "fn": funding_sentiment, "params": {"period": 14, "threshold": 2.0}},
        {"id": "FUNDING_5_5",   "name": "费率反转 5/5%",  "fn": funding_sentiment, "params": {"period": 5, "threshold": 5.0}},
    ]

def oi_variants():
    return [
        {"id": "OI_10", "name": "OI量价 10 确认", "fn": open_interest_breakout, "params": {"period": 10}},
        {"id": "OI_14", "name": "OI量价 14 确认", "fn": open_interest_breakout, "params": {"period": 14}},
    ]

def triple_confirm_variants():
    return [
        {"id": "TRIPLE_5_20_14_20",  "name": "三重确认 5/20/14/20",  "fn": triple_confirm, "params": {"ma_fast": 5, "ma_slow": 20, "rsi_period": 14, "vol_period": 20}},
        {"id": "TRIPLE_3_10_7_10",   "name": "三重确认 3/10/7/10",   "fn": triple_confirm, "params": {"ma_fast": 3, "ma_slow": 10, "rsi_period": 7, "vol_period": 10}},
        {"id": "TRIPLE_8_21_14_20",  "name": "三重确认 8/21/14/20",  "fn": triple_confirm, "params": {"ma_fast": 8, "ma_slow": 21, "rsi_period": 14, "vol_period": 20}},
        {"id": "TRIPLE_10_30_14_20", "name": "三重确认 10/30/14/20", "fn": triple_confirm, "params": {"ma_fast": 10, "ma_slow": 30, "rsi_period": 14, "vol_period": 20}},
    ]

def bb_macd_variants():
    return [
        {"id": "BB_MACD_20_2_12_26_9", "name": "BB+MACD 20/2/12/26/9", "fn": bb_macd_combo, "params": {"bb_period": 20, "bb_std": 2.0, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9}},
        {"id": "BB_MACD_14_2_8_17_9",  "name": "BB+MACD 14/2/8/17/9",  "fn": bb_macd_combo, "params": {"bb_period": 14, "bb_std": 2.0, "macd_fast": 8, "macd_slow": 17, "macd_signal": 9}},
        {"id": "BB_MACD_20_2_5_13_5",  "name": "BB+MACD 20/2/5/13/5",  "fn": bb_macd_combo, "params": {"bb_period": 20, "bb_std": 2.0, "macd_fast": 5, "macd_slow": 13, "macd_signal": 5}},
    ]

def rsi_vol_variants():
    return [
        {"id": "RSI_VOL_14_70_30_20", "name": "RSI+量 14 共振", "fn": rsi_volume_combo, "params": {"rsi_period": 14, "overbought": 70, "oversold": 30, "vol_period": 20}},
        {"id": "RSI_VOL_7_80_20_10",  "name": "RSI+量 7 共振",  "fn": rsi_volume_combo, "params": {"rsi_period": 7, "overbought": 80, "oversold": 20, "vol_period": 10}},
        {"id": "RSI_VOL_21_65_35_20", "name": "RSI+量 21 共振", "fn": rsi_volume_combo, "params": {"rsi_period": 21, "overbought": 65, "oversold": 35, "vol_period": 20}},
    ]

def kdj_macd_variants():
    return [
        {"id": "KDJ_MACD_9_3_20_80_12_26_9", "name": "KDJ+MACD 9/3 共振", "fn": kdj_macd_combo, "params": {"k_period": 9, "d_period": 3, "oversold": 20, "overbought": 80, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9}},
        {"id": "KDJ_MACD_5_3_25_75_8_17_9",  "name": "KDJ+MACD 5/3 共振", "fn": kdj_macd_combo, "params": {"k_period": 5, "d_period": 3, "oversold": 25, "overbought": 75, "macd_fast": 8, "macd_slow": 17, "macd_signal": 9}},
        {"id": "KDJ_MACD_14_3_20_80_5_13_5", "name": "KDJ+MACD 14/3 共振","fn": kdj_macd_combo, "params": {"k_period": 14, "d_period": 3, "oversold": 20, "overbought": 80, "macd_fast": 5, "macd_slow": 13, "macd_signal": 5}},
    ]


def adx_variants():
    return [
        {"id": "ADX_14", "name": "ADX 14 趋势强度", "fn": adx_trend, "params": {"period": 14}},
        {"id": "ADX_10", "name": "ADX 10 趋势强度", "fn": adx_trend, "params": {"period": 10}},
        {"id": "ADX_20", "name": "ADX 20 趋势强度", "fn": adx_trend, "params": {"period": 20}},
        {"id": "ADX_7",  "name": "ADX 7 趋势强度",  "fn": adx_trend, "params": {"period": 7}},
    ]

def supertrend_variants():
    return [
        {"id": "ST_10_3", "name": "Supertrend 10/3", "fn": supertrend, "params": {"period": 10, "mult": 3.0}},
        {"id": "ST_7_3",  "name": "Supertrend 7/3",  "fn": supertrend, "params": {"period": 7, "mult": 3.0}},
        {"id": "ST_14_2", "name": "Supertrend 14/2", "fn": supertrend, "params": {"period": 14, "mult": 2.0}},
        {"id": "ST_10_2", "name": "Supertrend 10/2", "fn": supertrend, "params": {"period": 10, "mult": 2.0}},
        {"id": "ST_20_3", "name": "Supertrend 20/3", "fn": supertrend, "params": {"period": 20, "mult": 3.0}},
    ]

def mfi_variants():
    return [
        {"id": "MFI_14_80_20", "name": "MFI 14 (20/80)", "fn": mfi_reversal, "params": {"period": 14, "overbought": 80, "oversold": 20}},
        {"id": "MFI_10_75_25", "name": "MFI 10 (25/75)", "fn": mfi_reversal, "params": {"period": 10, "overbought": 75, "oversold": 25}},
        {"id": "MFI_7_85_15",  "name": "MFI 7 (15/85)",  "fn": mfi_reversal, "params": {"period": 7, "overbought": 85, "oversold": 15}},
        {"id": "MFI_21_70_30", "name": "MFI 21 (30/70)", "fn": mfi_reversal, "params": {"period": 21, "overbought": 70, "oversold": 30}},
    ]

def ichimoku_variants():
    return [
        {"id": "ICHI_9_26_52",  "name": "Ichimoku 9/26/52",  "fn": ichimoku, "params": {"tenkan": 9, "kijun": 26, "senkou_b": 52}},
        {"id": "ICHI_7_22_44",  "name": "Ichimoku 7/22/44",  "fn": ichimoku, "params": {"tenkan": 7, "kijun": 22, "senkou_b": 44}},
        {"id": "ICHI_5_20_40",  "name": "Ichimoku 5/20/40",  "fn": ichimoku, "params": {"tenkan": 5, "kijun": 20, "senkou_b": 40}},
    ]

def keltner_variants():
    return [
        {"id": "KELT_20_14_2",  "name": "Keltner 20/14/2", "fn": keltner_breakout, "params": {"ema_period": 20, "atr_period": 14, "mult": 2.0}},
        {"id": "KELT_20_10_2",  "name": "Keltner 20/10/2", "fn": keltner_breakout, "params": {"ema_period": 20, "atr_period": 10, "mult": 2.0}},
        {"id": "KELT_14_14_15", "name": "Keltner 14/14/1.5","fn": keltner_breakout, "params": {"ema_period": 14, "atr_period": 14, "mult": 1.5}},
        {"id": "KELT_10_10_2",  "name": "Keltner 10/10/2", "fn": keltner_breakout, "params": {"ema_period": 10, "atr_period": 10, "mult": 2.0}},
    ]


# ═══════════════════════════════════════════
# 投票组合策略（追求高胜率，牺牲数量）
# ═══════════════════════════════════════════

def voting_ensemble(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    多策略投票：5条独立策略各自投票，≥N票同向才开仓。
    params: votes_needed (需要的最少票数, 默认4)
    5位评委: MA_cross, EMA_cross, RSI, BB, MACD
    """
    votes_needed = params.get("votes_needed", 4)
    df = df.copy()

    # 评委1: MA 5/20
    ma_fast = df["close"].rolling(5).mean()
    ma_slow = df["close"].rolling(20).mean()
    vote1 = np.where(ma_fast > ma_slow, 1, np.where(ma_fast < ma_slow, -1, 0))

    # 评委2: EMA 8/21
    ema_fast = df["close"].ewm(span=8, adjust=False).mean()
    ema_slow = df["close"].ewm(span=21, adjust=False).mean()
    vote2 = np.where(ema_fast > ema_slow, 1, np.where(ema_fast < ema_slow, -1, 0))

    # 评委3: RSI 14 (超卖30→看涨, 超买70→看跌)
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean().replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    vote3 = np.where(rsi < 30, 1, np.where(rsi > 70, -1, 0))

    # 评委4: BB 20/2
    bb_ma = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    bb_upper = bb_ma + 2.0 * bb_std
    bb_lower = bb_ma - 2.0 * bb_std
    vote4 = np.where(df["close"] < bb_lower, 1, np.where(df["close"] > bb_upper, -1, 0))

    # 评委5: MACD 12/26/9
    macd_f = df["close"].ewm(span=12, adjust=False).mean()
    macd_s = df["close"].ewm(span=26, adjust=False).mean()
    macd = macd_f - macd_s
    macd_sig = macd.ewm(span=9, adjust=False).mean()
    hist = macd - macd_sig
    vote5 = np.where(hist > 0, 1, np.where(hist < 0, -1, 0))

    # 计票
    total_up = (vote1 == 1).astype(int) + (vote2 == 1).astype(int) + (vote3 == 1).astype(int) + (vote4 == 1).astype(int) + (vote5 == 1).astype(int)
    total_down = (vote1 == -1).astype(int) + (vote2 == -1).astype(int) + (vote3 == -1).astype(int) + (vote4 == -1).astype(int) + (vote5 == -1).astype(int)

    df["signal"] = np.where(total_up >= votes_needed, 1,
                   np.where(total_down >= votes_needed, -1, 0))
    return df


def voting_ensemble_7(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    7 策略投票：MA, EMA, RSI, BB, MACD, KDJ, CCI 各一票，≥5票同向才开仓。
    """
    votes_needed = params.get("votes_needed", 5)
    df = df.copy()

    # 评委1-5 同上
    ma_f = df["close"].rolling(5).mean(); ma_s = df["close"].rolling(20).mean()
    v1 = np.where(ma_f > ma_s, 1, np.where(ma_f < ma_s, -1, 0))
    ema_f = df["close"].ewm(span=8, adjust=False).mean(); ema_s = df["close"].ewm(span=21, adjust=False).mean()
    v2 = np.where(ema_f > ema_s, 1, np.where(ema_f < ema_s, -1, 0))
    d = df["close"].diff(); g = d.where(d>0,0.0); l = (-d.where(d<0,0.0))
    r = 100-(100/(1+g.rolling(14).mean()/l.rolling(14).mean().replace(0,np.nan)))
    v3 = np.where(r<30,1,np.where(r>70,-1,0))
    bm = df["close"].rolling(20).mean(); bs = df["close"].rolling(20).std()
    v4 = np.where(df["close"]<bm-2*bs,1,np.where(df["close"]>bm+2*bs,-1,0))
    mf=df["close"].ewm(span=12,adjust=False).mean();ms=df["close"].ewm(span=26,adjust=False).mean();h=(mf-ms)-(mf-ms).ewm(span=9,adjust=False).mean()
    v5 = np.where(h>0,1,np.where(h<0,-1,0))

    # 评委6: KDJ 9/3
    lm = df["low"].rolling(9).min(); hm = df["high"].rolling(9).max()
    k = (df["close"]-lm)/(hm-lm+1e-10)*100; d_k = k.rolling(3).mean()
    v6 = np.where(k<20,1,np.where(k>80,-1,0))

    # 评委7: CCI 14
    tp = (df["high"]+df["low"]+df["close"])/3; ma_tp = tp.rolling(14).mean()
    mad = tp.rolling(14).apply(lambda x: np.abs(x-x.mean()).mean())
    cci = (tp-ma_tp)/(0.015*mad+1e-10)
    v7 = np.where(cci<-100,1,np.where(cci>100,-1,0))

    up = (v1==1).astype(int)+(v2==1).astype(int)+(v3==1).astype(int)+(v4==1).astype(int)+(v5==1).astype(int)+(v6==1).astype(int)+(v7==1).astype(int)
    dn = (v1==-1).astype(int)+(v2==-1).astype(int)+(v3==-1).astype(int)+(v4==-1).astype(int)+(v5==-1).astype(int)+(v6==-1).astype(int)+(v7==-1).astype(int)

    df["signal"] = np.where(up>=votes_needed,1,np.where(dn>=votes_needed,-1,0))
    return df


def voting_variants():
    return [
        {"id": "VOTE5_4",   "name": "5评委≥4票 投票", "fn": voting_ensemble,   "params": {"votes_needed": 4}},
        {"id": "VOTE5_3",   "name": "5评委≥3票 投票", "fn": voting_ensemble,   "params": {"votes_needed": 3}},
        {"id": "VOTE5_5",   "name": "5评委全票 投票", "fn": voting_ensemble,   "params": {"votes_needed": 5}},
        {"id": "VOTE7_5",   "name": "7评委≥5票 投票", "fn": voting_ensemble_7, "params": {"votes_needed": 5}},
        {"id": "VOTE7_6",   "name": "7评委≥6票 投票", "fn": voting_ensemble_7, "params": {"votes_needed": 6}},
        {"id": "VOTE7_7",   "name": "7评委全票 投票", "fn": voting_ensemble_7, "params": {"votes_needed": 7}},
    ]


def all_strategies() -> list[dict]:
    return (
        ma_variants() + extended_ma_variants() +
        ema_variants() + extended_ema_variants() +
        macd_variants() +
        rsi_variants() + extended_rsi_variants() +
        stochastic_variants() + extended_stoch_variants() +
        cci_variants() + extended_cci_variants() +
        bb_variants() + extended_bb_variants() +
        donchian_variants() + atr_variants() + extended_atr_variants() +
        volume_variants() + extended_volume_variants() +
        momentum_variants() + extended_momentum_variants() +
        ema_rsi_variants() + bb_rsi_variants() +
        ma_vol_variants() + psar_variants() + multi_ma_variants() +
        obv_variants() + funding_variants() + oi_variants() +
        triple_confirm_variants() + bb_macd_variants() +
        rsi_vol_variants() + kdj_macd_variants() +
        adx_variants() + supertrend_variants() + mfi_variants() +
        ichimoku_variants() + keltner_variants() + voting_variants()
    )


STRATEGIES = all_strategies()
