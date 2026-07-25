"""
Gate.io REST API 数据获取 + 模拟数据降级
- 实时 ticker: /api/v4/spot/tickers
- K 线数据:   /api/v4/spot/candlesticks
- 使用 urllib（不用 aiohttp，避免 Windows 上 aiodns 问题）
"""
import asyncio
import json
import logging
import time
import ssl
import urllib.request
import websockets
import pandas as pd
from config import GATE_BASE, BINANCE_BASE, OKX_BASE, DATA_PROVIDER
from simulator import generate_ticker as sim_ticker, generate_candles as sim_candles

# 复用 SSL context，避免每次请求都握手
_ssl_context = ssl.create_default_context()
_ssl_context.check_hostname = False
_ssl_context.verify_mode = ssl.CERT_NONE

logger = logging.getLogger("gate_client")

# 数据源模式
SOURCE_LIVE = "LIVE"
SOURCE_SIMULATED = "SIMULATED"
_data_source = SOURCE_LIVE
_fail_count: dict[str, int] = {"ticker": 0, "candles": 0}
_FAIL_THRESHOLD = 10  # 提高容错，避免网络抖动误切模拟

_on_source_change: list[callable] = []
_retry_count: int = 0  # 模拟模式下定期重试实时 API 的计数


def _http_get(url: str, timeout: int = 10) -> dict | list | None:
    """同步 HTTP GET，在线程池中运行"""
    import socket
    req = urllib.request.Request(url, headers={"User-Agent": "EventContractSim/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (OSError, TimeoutError, ConnectionError) as e:
        # 网络瞬断不打印完整traceback
        raise ConnectionError(f"Gate.io unreachable: {e}") from None


async def _http_get_async(url: str, timeout: int = 10):
    """异步 HTTP GET"""
    return await asyncio.to_thread(_http_get, url, timeout)


def _switch_to_simulated(reason: str):
    global _data_source
    if _data_source == SOURCE_SIMULATED:
        return
    _data_source = SOURCE_SIMULATED
    logger.warning(f"切换到模拟数据: {reason}")
    for cb in _on_source_change:
        try: cb(_data_source)
        except Exception: pass


def _try_switch_to_live():
    """如果实时 API 恢复，自动切回 LIVE"""
    global _data_source, _retry_count
    if _data_source == SOURCE_LIVE:
        return
    _retry_count += 1
    # 每 30 次调用重试一次（约每分钟，避免频繁请求）
    if _retry_count % 30 != 0:
        return
    try:
        if DATA_PROVIDER == "binance":
            url = f"{BINANCE_BASE}/fapi/v1/ticker/price?symbol=BTCUSDT"
        else:
            url = f"{GATE_BASE}/api/v4/futures/usdt/tickers?contract=BTC_USDT"
        data = _http_get(url, timeout=5)
        if data and isinstance(data, list) and len(data) > 0:
            float(data[0]["last"])  # 验证数据有效
            _data_source = SOURCE_LIVE
            for k in _fail_count:
                _fail_count[k] = 0
            logger.info("实时 API 已恢复，切回 LIVE 模式")
            for cb in _on_source_change:
                try: cb(_data_source)
                except Exception: pass
    except Exception:
        pass


def get_data_source() -> str:
    return _data_source


def get_data_source_info() -> dict:
    return {
        "source": _data_source,
        "live_available": _data_source == SOURCE_LIVE,
        "ticker_failures": _fail_count["ticker"],
        "candles_failures": _fail_count["candles"],
    }


def on_source_change(callback):
    _on_source_change.append(callback)


# ═══════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════

async def fetch_ticker(symbol: str = "") -> dict | None:
    """获取单个品种最新成交价。支持 Binance/Gate.io。"""
    if _data_source == SOURCE_SIMULATED:
        _try_switch_to_live()
        return sim_ticker(symbol)

    # OKX 永续合约 ticker
    if DATA_PROVIDER == "okx":
        okx_sym = symbol.replace("_", "-")  # BTC_USDT → BTC-USDT
        url = f"{OKX_BASE}/api/v5/market/ticker?instId={okx_sym}-SWAP"
        try:
            data = await _http_get_async(url, timeout=5)
            d = data["data"][0]
            _fail_count["ticker"] = 0
            return {"symbol": symbol, "price": float(d["last"]), "mark_price": float(d["last"]), "index_price": float(d["last"]), "time": time.time()}
        except Exception as e:
            _fail_count["ticker"] += 1
            if _fail_count["ticker"] >= _FAIL_THRESHOLD:
                _switch_to_simulated(f"ticker fail: {e}")
            return sim_ticker(symbol)

    # Binance ticker# OKX K 线
    if DATA_PROVIDER == "okx":
        okx_sym = symbol.replace("_", "-")
        url = f"{OKX_BASE}/api/v5/market/candles?instId={okx_sym}-SWAP&bar={interval}&limit={limit}"
        data = None
        for attempt in range(2):
            try:
                data = await _http_get_async(url, timeout=15)
                break
            except Exception:
                if attempt == 0: await asyncio.sleep(1)
        if data is None:
            _fail_count["candles"] += 1
            if _fail_count["candles"] >= _FAIL_THRESHOLD:
                _switch_to_simulated("candles fail")
            return sim_candles(symbol, interval, limit, seed=seed)
        rows = []
        for d in data.get("data", []):
            try:
                rows.append({"time": int(d[0])//1000, "open": float(d[1]), "high": float(d[2]), "low": float(d[3]), "close": float(d[4]), "volume": float(d[5])})
            except: continue
        df = pd.DataFrame(rows)
        if not df.empty:
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.sort_values("time").reset_index(drop=True)
        _fail_count["candles"] = 0
        return df

    # Binance K 线
# OKX K 线
    if DATA_PROVIDER == "okx":
        okx_sym = symbol.replace("_", "-")
        url = f"{OKX_BASE}/api/v5/market/candles?instId={okx_sym}-SWAP&bar={interval}&limit={limit}"
        data = None
        for attempt in range(2):
            try:
                data = await _http_get_async(url, timeout=15)
                break
            except Exception:
                if attempt == 0: await asyncio.sleep(1)
        if data is None:
            _fail_count["candles"] += 1
            if _fail_count["candles"] >= _FAIL_THRESHOLD:
                _switch_to_simulated("candles fail")
            return sim_candles(symbol, interval, limit, seed=seed)
        rows = []
        for d in data.get("data", []):
            try:
                rows.append({"time": int(d[0])//1000, "open": float(d[1]), "high": float(d[2]), "low": float(d[3]), "close": float(d[4]), "volume": float(d[5])})
            except: continue
        df = pd.DataFrame(rows)
        if not df.empty:
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.sort_values("time").reset_index(drop=True)
        _fail_count["candles"] = 0
        return df

    # Binance K 线
    if DATA_PROVIDER == "binance":
        bin_sym = symbol.replace("_", "")
        url = f"{BINANCE_BASE}/fapi/v1/klines?symbol={bin_sym}&interval={interval}&limit={limit}"
        try:
            data = await _http_get_async(url, timeout=5)
            _fail_count["ticker"] = 0
            return {
                "symbol": symbol,
                "price": float(data["price"]),
                "mark_price": float(data["price"]),
                "index_price": float(data["price"]),
                "time": time.time(),
            }
        except Exception as e:
            _fail_count["ticker"] += 1
            if _fail_count["ticker"] >= _FAIL_THRESHOLD:
                _switch_to_simulated(f"ticker 连续 {_FAIL_THRESHOLD} 次失败: {e}")
            return sim_ticker(symbol)

    # Gate.io 合约 ticker
    url = f"{GATE_BASE}/api/v4/futures/usdt/tickers?contract={symbol}"
    try:
        data = await _http_get_async(url, timeout=5)
        if not data or not isinstance(data, list):
            raise ValueError("空响应")
        _fail_count["ticker"] = 0
        d = data[0]
        return {
            "symbol": symbol,
            "price": float(d["last"]),
            "mark_price": float(d.get("mark_price", d["last"])),
            "index_price": float(d.get("index_price", d.get("last", 0))),
            "time": float(d.get("create_time_ms", time.time() * 1000)) / 1000,
        }
    except Exception as e:
        _fail_count["ticker"] += 1
        if _fail_count["ticker"] >= _FAIL_THRESHOLD:
            _switch_to_simulated(f"ticker 连续 {_FAIL_THRESHOLD} 次失败: {e}")
        return sim_ticker(symbol)


async def fetch_candles(session=None, symbol="", interval="1m", limit=1000, seed=None):
    """获取 K 线数据。session 参数保留兼容性但不使用。"""
    if _data_source == SOURCE_SIMULATED:
        _try_switch_to_live()  # 定期尝试重连
        return sim_candles(symbol, interval, limit, seed=seed)
# OKX K 线
    if DATA_PROVIDER == "okx":
        okx_sym = symbol.replace("_", "-")
        url = f"{OKX_BASE}/api/v5/market/candles?instId={okx_sym}-SWAP&bar={interval}&limit={limit}"
        data = None
        for attempt in range(2):
            try:
                data = await _http_get_async(url, timeout=15)
                break
            except Exception:
                if attempt == 0: await asyncio.sleep(1)
        if data is None:
            _fail_count["candles"] += 1
            if _fail_count["candles"] >= _FAIL_THRESHOLD:
                _switch_to_simulated("candles fail")
            return sim_candles(symbol, interval, limit, seed=seed)
        rows = []
        for d in data.get("data", []):
            try:
                rows.append({"time": int(d[0])//1000, "open": float(d[1]), "high": float(d[2]), "low": float(d[3]), "close": float(d[4]), "volume": float(d[5])})
            except: continue
        df = pd.DataFrame(rows)
        if not df.empty:
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.sort_values("time").reset_index(drop=True)
        _fail_count["candles"] = 0
        return df

    # Binance K 线
# OKX K 线
    if DATA_PROVIDER == "okx":
        okx_sym = symbol.replace("_", "-")
        url = f"{OKX_BASE}/api/v5/market/candles?instId={okx_sym}-SWAP&bar={interval}&limit={limit}"
        data = None
        for attempt in range(2):
            try:
                data = await _http_get_async(url, timeout=15)
                break
            except Exception:
                if attempt == 0: await asyncio.sleep(1)
        if data is None:
            _fail_count["candles"] += 1
            if _fail_count["candles"] >= _FAIL_THRESHOLD:
                _switch_to_simulated("candles fail")
            return sim_candles(symbol, interval, limit, seed=seed)
        rows = []
        for d in data.get("data", []):
            try:
                rows.append({"time": int(d[0])//1000, "open": float(d[1]), "high": float(d[2]), "low": float(d[3]), "close": float(d[4]), "volume": float(d[5])})
            except: continue
        df = pd.DataFrame(rows)
        if not df.empty:
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.sort_values("time").reset_index(drop=True)
        _fail_count["candles"] = 0
        return df

    # Binance K 线
    if DATA_PROVIDER == "binance":
        bin_sym = symbol.replace("_", "")
        url = f"{BINANCE_BASE}/fapi/v1/klines?symbol={bin_sym}&interval={interval}&limit={limit}"
    else:
        url = f"{GATE_BASE}/api/v4/futures/usdt/candlesticks?contract={symbol}&interval={interval}&limit={limit}"
    # 重试 1 次（网络瞬断容错）
    data = None
    last_err = None
    for attempt in range(2):
        try:
            data = await _http_get_async(url, timeout=15)
            break
        except Exception as e:
            last_err = e
            if attempt == 0:
                await asyncio.sleep(1)  # 等 1 秒再试
    if data is None:
        _fail_count["candles"] += 1
        if _fail_count["candles"] >= _FAIL_THRESHOLD:
            _switch_to_simulated(f"candles 连续 {_FAIL_THRESHOLD} 次失败: {last_err}")
        return sim_candles(symbol, interval, limit, seed=seed)

    rows = []
    is_binance = DATA_PROVIDER == "binance"
    for d in data:
        try:
            if is_binance:
                rows.append({"time": int(d[0])//1000, "open": float(d[1]), "high": float(d[2]), "low": float(d[3]), "close": float(d[4]), "volume": float(d[5])})
            elif isinstance(d, dict):
                # 合约 K 线返回 dict 格式: {t, o, h, l, c, v}
                rows.append({
                    "time": int(d["t"]),
                    "volume": float(d["v"]),
                    "close": float(d["c"]),
                    "high": float(d["h"]),
                    "low": float(d["l"]),
                    "open": float(d["o"]),
                })
            else:
                # 现货 K 线返回 list 格式: [time, volume, close, high, low, open]
                rows.append({
                    "time": int(d[0]),
                    "volume": float(d[1]),
                    "close": float(d[2]),
                    "high": float(d[3]),
                    "low": float(d[4]),
                    "open": float(d[5]),
                })
        except (IndexError, ValueError, TypeError, KeyError):
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    _fail_count["candles"] = 0
    return df


# ═══════════════════════════════════════════
# WebSocket 实时价格推送（OKX）
# ═══════════════════════════════════════════

async def ws_price_stream(prices_dict: dict, mark_prices_dict: dict | None = None, symbols: list[str] | None = None):
    """OKX WebSocket 实时价格流。同时获取 last 价和标记价。断线自动重连。"""
    if symbols is None:
        from config import SYMBOLS as symbols
    mapping = {s.replace("_", "-") + "-SWAP": s for s in symbols}
    ws_url = "wss://ws.okx.com:8443/ws/v5/public"

    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20) as ws:
                # 订阅 tickers + mark-price
                args = [{"channel": "tickers", "instId": k} for k in mapping]
                args += [{"channel": "mark-price", "instId": k} for k in mapping]
                await ws.send(json.dumps({"op": "subscribe", "args": args}))
                _fail_count["ticker"] = 0

                async for msg in ws:
                    try:
                        data = json.loads(msg)
                        ch = data.get("arg", {}).get("channel", "")
                        if ch == "tickers" and "data" in data:
                            for item in data["data"]:
                                inst_id = item["instId"]
                                if inst_id in mapping:
                                    sym = mapping[inst_id]
                                    prices_dict[sym] = float(item["last"])
                        elif ch == "mark-price" and "data" in data and mark_prices_dict is not None:
                            for item in data["data"]:
                                inst_id = item["instId"]
                                if inst_id in mapping:
                                    sym = mapping[inst_id]
                                    mark_prices_dict[sym] = float(item["markPrice"])
                    except Exception:
                        pass
        except Exception as e:
            _fail_count["ticker"] += 1
            logger.warning(f"WebSocket 断开，3秒后重连: {e}")
            await asyncio.sleep(3)


# 兼容旧调用（不再需要 session 参数）
def make_session():
    class _Dummy:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
    return _Dummy()
