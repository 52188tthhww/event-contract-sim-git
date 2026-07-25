"""
模拟数据生成器 — Gate.io API 不可用时的降级方案
- ticker: 只按真实时间步进（每次 2s），价格稳定
- candles: 支持确定性种子，回测结果可复现
"""
import time
import random
import math
import hashlib
from datetime import datetime, timezone, timedelta
import pandas as pd

# 初始种子价格
SEEDS = {
    "BTC_USDT": 62000.0,
    "ETH_USDT": 1740.0,
}

# 年化波动率
VOLATILITY = {
    "BTC_USDT": 0.60,
    "ETH_USDT": 0.80,
}

# ── 实时价格状态（仅 ticker 更新）──
_live_price: dict[str, float] = {}
_last_tick: dict[str, float] = {}


def _init_live(symbol: str):
    now = time.time()
    if symbol not in _live_price:
        _live_price[symbol] = SEEDS.get(symbol, 50000.0)
        _last_tick[symbol] = now


def _make_seeded_random(seed: str) -> random.Random:
    """用字符串种子创建独立的随机数生成器"""
    digest = hashlib.sha256(seed.encode()).digest()
    int_seed = int.from_bytes(digest[:8], 'big')
    return random.Random(int_seed)


def _rw_step(rng: random.Random, price: float, vol: float, dt_days: float) -> float:
    """几何布朗运动一步，返回新价格"""
    if dt_days <= 0:
        return price
    sigma = vol * math.sqrt(dt_days)
    epsilon = rng.gauss(0, 1)
    drift = -0.5 * sigma * sigma * dt_days
    return price * math.exp(drift + sigma * epsilon)


def generate_ticker(symbol: str) -> dict:
    """
    模拟 ticker — 只按真实流逝时间推进价格。
    """
    _init_live(symbol)
    vol = VOLATILITY.get(symbol, 0.6)
    now = time.time()
    elapsed = min(now - _last_tick[symbol], 5.0)
    dt_days = elapsed / 86400.0

    rng = random  # ticker 用系统随机（不可预测）
    _live_price[symbol] = _rw_step(rng, _live_price[symbol], vol, dt_days)
    _last_tick[symbol] = now

    return {
        "symbol": symbol,
        "price": round(_live_price[symbol], 2),
        "time": now,
    }


def generate_candles(
    symbol: str,
    interval: str = "1m",
    limit: int = 1000,
    seed: str | None = None,
) -> pd.DataFrame:
    """
    模拟 K 线 — 从当前实时价格快照向后生成历史。
    seed=None → 随机（交易用）；seed="xxx" → 确定性（回测用），同seed同结果。
    """
    _init_live(symbol)
    vol = VOLATILITY.get(symbol, 0.6)
    now = datetime.now(timezone.utc)

    # 确定性种子：回测可复现
    rng = _make_seeded_random(seed) if seed else random
    # 有种子时从固定价格起步（不受 ticker 实时波动干扰），否则用实时价
    if seed:
        price = SEEDS.get(symbol, 50000.0)
    else:
        price = _live_price[symbol]

    total_steps = limit * 4
    dt_per_step = 1.0 / 1440 / 4

    path = [price]
    for _ in range(total_steps):
        price = _rw_step(rng, price, vol, dt_per_step)
        path.append(price)

    path.reverse()

    rows = []
    for bar_i in range(limit):
        t = now - timedelta(minutes=limit - bar_i)
        bar_path = path[bar_i * 4 : (bar_i + 1) * 4 + 1]
        open_p = bar_path[0]
        close_p = bar_path[-1]
        high = max(bar_path)
        low = min(bar_path)
        volume = abs(rng.gauss(50, 20))

        rows.append({
            "time": int(t.timestamp()),
            "open": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close_p, 2),
            "volume": round(volume, 2),
        })

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.sort_values("time").reset_index(drop=True)
    return df
