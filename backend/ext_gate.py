"""
扩展数据获取 — fetch_fine_bars, fetch_candles_paged
挂载到 gate_client 模块，不修改原始 gate_client.py
"""
import asyncio
import pandas as pd
from config import OKX_BASE
from gate_client import _http_get_async, _fail_count, _FAIL_THRESHOLD, _switch_to_simulated
from simulator import generate_candles as sim_candles


async def fetch_candles_paged(symbol: str, interval: str = "1s", total_bars: int = 3600) -> pd.DataFrame:
    """分页拉取 OKX K 线（用于 1s 粒度，每页最多 300 根）。"""
    okx_sym = symbol.replace("_", "-")
    all_rows = []
    after = ""
    remaining = total_bars
    _max_pages = 50

    for _page in range(_max_pages):
        if remaining <= 0:
            break
        page_limit = min(remaining, 300)
        url = f"{OKX_BASE}/api/v5/market/candles?instId={okx_sym}-SWAP&bar={interval}&limit={page_limit}"
        if after:
            url += f"&after={after}"

        data = None
        for attempt in range(2):
            try:
                data = await _http_get_async(url, timeout=15)
                break
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(1)

        if data is None or "data" not in data or not data["data"]:
            break

        candles = data["data"]
        for d in candles:
            try:
                all_rows.append({
                    "time": int(d[0]) // 1000,
                    "open": float(d[1]), "high": float(d[2]),
                    "low": float(d[3]), "close": float(d[4]),
                    "volume": float(d[5]),
                })
            except (IndexError, ValueError):
                continue

        if len(candles) < page_limit:
            break
        after = candles[-1][0]
        remaining -= page_limit

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.sort_values("time").reset_index(drop=True)
    return df


async def fetch_fine_bars(symbol: str, bar_seconds: int = 15, minute_window: int = 60) -> pd.DataFrame:
    """拉取 OKX 1s K 线并重采样到指定秒级，用于精确回测。"""
    total_1s_bars = minute_window * 60
    df_1s = await fetch_candles_paged(symbol, "1s", total_1s_bars)

    if df_1s.empty:
        _fail_count["candles"] += 1
        if _fail_count["candles"] >= _FAIL_THRESHOLD:
            _switch_to_simulated("fine bars fail")
        return sim_candles(symbol, f"{bar_seconds}s", minute_window * 60 // bar_seconds)

    _fail_count["candles"] = 0
    df_1s = df_1s.set_index("time")
    df_resampled = (df_1s.resample(f"{bar_seconds}s")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna().reset_index())
    return df_resampled
