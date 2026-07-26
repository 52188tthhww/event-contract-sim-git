"""
事件合约模拟交易系统 — FastAPI 后端入口
调度器：价格轮询(2s) + 自动回测(60s) + 模拟跟单
"""
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    SYMBOLS,
    POLL_INTERVAL,
    BACKTEST_INTERVAL,
    CONTRACT_DURATIONS,
    DEFAULT_CANDLE_LIMIT,
    CANDLE_INTERVAL,
)
from state import app_state
from db import init_db, save_report, get_db, save_locked_strategies, load_locked_strategies, save_tick
from gate_client import fetch_ticker, fetch_candles, get_data_source_info, on_source_change, ws_price_stream
from backtest import evaluate_all, evaluate_all_dual
from strategies import STRATEGIES
from trader import open_position, get_open_positions, get_closed_positions, get_position_summary


# ───────────────────── 调度任务 ─────────────────────

async def price_poller():
    """每 2 秒批量拉取 BTC/ETH 价格。单品种失败不影响其他。"""
    _pf = 0
    while True:
        try:
            for sym in SYMBOLS:
                tick = await fetch_ticker(symbol=sym)
                if tick:
                    app_state["prices"][sym] = tick["price"]
                    app_state.setdefault("mark_prices", {})[sym] = tick.get("mark_price", tick["price"])
                    try:
                        db = await get_db()
                        if gc._data_source == gc.SOURCE_LIVE:
                            await save_tick(db, sym, tick["price"], int(time.time()))
                    except Exception:
                        pass
            _pf = 0
            if app_state["status"] == "PAUSED" and not app_state["pending_confirm"]:
                app_state["status"] = "RUNNING"
                app_state["events"].append({
                    "level": "INFO",
                    "msg": "🔄 数据恢复，系统自动继续运行",
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            _pf += 1
            if _pf >= 10:
                _pause_with_error(f"价格轮询连续 {_pf} 次异常: {e}")
            elif _pf == 1:
                app_state["events"].append({
                    "level": "WARN",
                    "msg": f"价格轮询异常: {e}",
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
        # 限制事件列表大小，防止内存泄漏
        if len(app_state["events"]) > 500:
            app_state["events"] = app_state["events"][-200:]
        if len(app_state["open_positions"]) > 200:
            app_state["open_positions"] = [p for p in app_state["open_positions"] if p["status"] == "OPEN"][-50:] + [p for p in app_state["open_positions"] if p["status"] == "CLOSED"][-100:]
        await asyncio.sleep(POLL_INTERVAL)


async def backtest_scheduler():
    """每 60 秒自动运行一次回测"""
    await asyncio.sleep(5)
    _consecutive_failures = 0
    while True:
        await asyncio.sleep(BACKTEST_INTERVAL)
        if app_state["status"] != "RUNNING":
            continue
        try:
            reports = []
            for sym in SYMBOLS:
                from ext_gate import fetch_fine_bars
                df_15s, df_1m = await asyncio.gather(
                    fetch_fine_bars(symbol=sym, bar_seconds=15, minute_window=180),
                    fetch_candles(symbol=sym, interval=CANDLE_INTERVAL, limit=DEFAULT_CANDLE_LIMIT),
                )
                if (df_15s is None or df_15s.empty) and (df_1m is None or df_1m.empty):
                    continue
                reps = evaluate_all_dual(df_15s, df_1m)
                reports.append({"symbol": sym, "reports": reps})

            if reports:
                app_state["last_reports"] = reports
                _consecutive_failures = 0
                app_state["events"].append({
                    "level": "INFO",
                    "msg": f"📊 自动回测完成 — {len(reports)} 品种",
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
            else:
                _consecutive_failures += 1
                if _consecutive_failures >= 3:
                    app_state["events"].append({
                        "level": "WARN",
                        "msg": f"⚠️ 自动回测连续 {_consecutive_failures} 次无数据，检查 Gate.io 连接",
                        "ts": datetime.now(timezone.utc).isoformat(),
                    })
        except Exception as e:
            _consecutive_failures += 1
            if _consecutive_failures >= 5:
                _pause_with_error(f"回测连续 {_consecutive_failures} 次异常: {e}")
            else:
                app_state["events"].append({
                    "level": "WARN",
                    "msg": f"回测调度异常 (连续{_consecutive_failures}次): {e}",
                    "ts": datetime.now(timezone.utc).isoformat(),
                })


async def live_trader():
    """按锁定策略实时检查信号并自动开仓。每策略绑定品种，同duration可多策略并行。"""
    await asyncio.sleep(10)
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        if app_state["status"] != "RUNNING":
            continue

        has_locked = any(len(v) > 0 for v in app_state["locked"].values())
        if not has_locked:
            continue

        try:
            from ext_gate import fetch_fine_bars
            cache_15s = {}
            cache_1m = {}
            for dur, strats in app_state["locked"].items():
                for strat in strats:
                    sym = strat.get("symbol", "BTC_USDT")
                    price = app_state["prices"].get(sym)
                    if price is None:
                        continue

                    exists = any(
                        p["symbol"] == sym
                        and p["duration"] == dur
                        and p["strategy_id"] == strat["id"]
                        and p["status"] == "OPEN"
                        for p in app_state["open_positions"]
                    )
                    if exists:
                        continue

                    # 3min→15s K线, 5/10min→1m K线（与观测池一致）
                    if dur == 3:
                        if sym not in cache_15s:
                            df = await fetch_fine_bars(symbol=sym, bar_seconds=15, minute_window=60)
                            cache_15s[sym] = df
                        else:
                            df = cache_15s[sym]
                    else:
                        if sym not in cache_1m:
                            df = await fetch_candles(symbol=sym, interval=CANDLE_INTERVAL, limit=50)
                            cache_1m[sym] = df
                        else:
                            df = cache_1m[sym]
                    if df is None or df.empty:
                        continue

                    try:
                        df_sig = strat["fn"](df.copy(), strat["params"])
                        shifted = df_sig["signal"].shift(1).fillna(0).astype(int)
                        last_signal = int(shifted.iloc[-1])
                    except Exception:
                        last_signal = 0

                    # 持续信号策略（MA/EMA/MACD等）：仅翻转时开仓
                    from ext_strategies import is_flip_strategy
                    if is_flip_strategy(strat["id"]):
                        prev = strat.get("_prev_sig", 0)
                        if last_signal == prev:
                            last_signal = 0
                        else:
                            strat["_prev_sig"] = last_signal
                        # 5/10min 加量确认
                        if last_signal != 0 and dur != 3:
                            vol_ma = df["volume"].rolling(20).mean()
                            if df["volume"].iloc[-1] <= vol_ma.iloc[-1]:
                                last_signal = 0

                    if last_signal != 0:
                        await open_position(
                            sym, dur, last_signal, price,
                            strat["id"], strat["name"],
                        )
        except Exception as e:
            app_state["events"].append({
                "level": "WARN",
                "msg": f"模拟交易轮询异常: {e}",
                "ts": datetime.now(timezone.utc).isoformat(),
            })


def _pause_with_error(msg: str):
    """异常时暂停系统，不阻塞恢复（网络恢复后可自动继续）"""
    app_state["status"] = "PAUSED"
    app_state["events"].append({
        "level": "ERROR",
        "msg": msg,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


# ───────────────────── 自动锁定策略 ─────────────────────

async def auto_lock_loop():
    """自动锁定策略循环：3m/5m/10m 并行，各自独立搜索-锁定-跟踪"""
    await asyncio.sleep(15)
    al = app_state["auto_lock"]

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        if not al["enabled"]:
            continue

        sym = al["symbol"]
        summary = get_position_summary()
        closed_all = summary["closed_count"]

        for dur in al.get("active_durations", CONTRACT_DURATIONS):
            ds = al["durations"][dur]

            # ── 搜索 ──
            if ds["status"] in ("idle", "searching"):
                ds["status"] = "searching"
                # 清掉该duration的旧锁定（只清自动锁的，保留手动锁的不动...这里直接清全部）
                app_state["locked"][dur] = [s for s in app_state["locked"][dur] if not _is_auto_locked(s, al)]

                # 用配置的回测窗口
                hours_list = al.get("backtest_hours", [1, 2])
                perfect = None
                for h in hours_list:
                    minute_window = h * 60
                    try:
                        from ext_gate import fetch_fine_bars
                        df_15s, df_1m = await asyncio.gather(
                            fetch_fine_bars(symbol=sym, bar_seconds=15, minute_window=minute_window),
                            fetch_candles(symbol=sym, interval=CANDLE_INTERVAL, limit=minute_window),
                        )
                        if (df_15s is None or df_15s.empty) and (df_1m is None or df_1m.empty):
                            continue
                        reports = evaluate_all_dual(df_15s, df_1m)
                    except Exception:
                        continue
                    min_wr = al.get("win_rate_threshold", 0.80)
                    min_trades = al.get("min_trades", 10)
                    reverse = al.get("reverse_mode", False)
                    if reverse:
                        perfect = [r for r in reports if r["duration"] == dur and r["win_rate"] <= min_wr and r["total_trades"] >= min_trades]
                    else:
                        perfect = [r for r in reports if r["duration"] == dur and r["win_rate"] >= min_wr and r["total_trades"] >= min_trades]
                    if perfect:
                        break

                if not perfect:
                    ds["status"] = "waiting"
                    app_state["events"].append({
                        "level": "INFO",
                        "msg": f"🤖 自动锁定 {dur}m: 1h/2h均无≥80%胜率策略，15秒后重试",
                        "ts": datetime.now(timezone.utc).isoformat(),
                    })
                    await asyncio.sleep(15)
                    ds["status"] = "searching"
                    continue
                best = max(perfect, key=lambda r: r["total_trades"])
                strat = next((s for s in STRATEGIES if s["id"] == best["strategy_id"]), None)
                if not strat:
                    continue

                locked_entry = {**strat, "symbol": sym, "_auto": True, "locked_at": datetime.now(timezone.utc).isoformat()}
                app_state["locked"][dur].append(locked_entry)
                ds["active_strategy"] = {"id": best["strategy_id"], "name": best["strategy_name"], "win_rate": best["win_rate"], "total_trades": best["total_trades"]}
                ds["status"] = "trading"
                ds["trade_count"] = 0
                ds["win_count"] = 0
                # 记录该策略已有的平仓数（防止旧记录被重复计算）
                closed = get_closed_positions()
                ds["_closed_snapshot"] = len([c for c in closed if c.get("strategy_id") == best["strategy_id"]])

                app_state["events"].append({
                    "level": "INFO",
                    "msg": f"🤖 自动锁定 {sym} {dur}m: {best['strategy_name']} 胜率{best['win_rate']*100:.0f}%/{best['total_trades']}笔",
                    "ts": datetime.now(timezone.utc).isoformat(),
                })

            # ── 交易中 ──
            elif ds["status"] == "trading":
                closed = get_closed_positions()
                # 新平仓且属于当前策略
                new_closed = [c for c in closed if c.get("strategy_id") == ds["active_strategy"]["id"]]
                detected = len(new_closed) - ds["_closed_snapshot"]
                if detected > 0:
                    latest = new_closed[-1]
                    pnl = latest.get("pnl", 0) or 0
                    ds["trade_count"] += 1
                    ds["last_trade_pnl"] = pnl
                    ds["_closed_snapshot"] = len(new_closed)

                    if pnl > 0:
                        ds["win_count"] += 1
                        ds["loss_streak"] = 0
                        app_state["events"].append({
                            "level": "INFO",
                            "msg": f"🤖 自动锁定 {sym} {dur}m #{ds['trade_count']}: ✅ WIN +{pnl:.2f}USDT 继续",
                            "ts": datetime.now(timezone.utc).isoformat(),
                        })
                    else:
                        ds["loss_streak"] = ds.get("loss_streak", 0) + 1
                        loss_enabled = al.get("loss_streak_enabled", True)
                        loss_max = al.get("loss_streak_max", 2)
                        if loss_enabled and ds["loss_streak"] >= loss_max:
                            app_state["locked"][dur] = [s for s in app_state["locked"][dur] if s.get("id") != ds["active_strategy"]["id"]]
                            ds["active_strategy"] = None
                            ds["status"] = "searching"
                            ds["loss_streak"] = 0
                            app_state["events"].append({
                                "level": "WARN",
                                "msg": f"🤖 自动锁定 {sym} {dur}m #{ds['trade_count']}: ❌ 连亏{loss_max}把，废弃策略",
                                "ts": datetime.now(timezone.utc).isoformat(),
                            })
                        else:
                            app_state["events"].append({
                                "level": "WARN",
                                "msg": f"🤖 自动锁定 {sym} {dur}m #{ds['trade_count']}: ❌ LOSE {pnl:.2f}USDT ({ds['loss_streak']}/{loss_max}) 继续",
                                "ts": datetime.now(timezone.utc).isoformat(),
                            })

            # ── 等待中（无操作）──
            elif ds["status"] == "waiting":
                pass


def _is_auto_locked(strat, al):
    return strat.get("_auto", False)



# ───────────────────── FastAPI 生命周期 ─────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 恢复上次锁定的策略
    try:
        saved = await load_locked_strategies({})
        for s in saved:
            dur = s["duration"]
            # 查找完整策略对象
            strat = next((st for st in STRATEGIES if st["id"] == s["strategy_id"]), None)
            if strat:
                entry = {**strat, "symbol": s.get("symbol", "BTC_USDT")}
                if s.get("_auto"):
                    entry["_auto"] = True
                app_state["locked"][dur].append(entry)
        total = sum(len(v) for v in app_state["locked"].values())
        if total > 0:
            app_state["events"].append({
                "level": "INFO",
                "msg": f"🔄 从数据库恢复了 {total} 条锁定策略",
                "ts": datetime.now(timezone.utc).isoformat(),
            })
    except Exception:
        pass

    def _on_source_change(new_source: str):
        app_state["events"].append({
            "level": "WARN",
            "msg": f"数据源切换 → {new_source}（{'🟢 实时' if new_source == 'LIVE' else '🟡 模拟'}）",
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    on_source_change(_on_source_change)

    asyncio.create_task(price_poller())
    asyncio.create_task(backtest_scheduler())
    asyncio.create_task(live_trader())
    asyncio.create_task(auto_lock_loop())

    # OKX WebSocket 实时价格流（替代轮询延迟）
    from config import DATA_PROVIDER
    if DATA_PROVIDER == "okx":
        app_state.setdefault("mark_prices", {})
        asyncio.create_task(ws_price_stream(app_state["prices"], app_state["mark_prices"], SYMBOLS))
    app_state["events"].append({
        "level": "INFO",
        "msg": "🚀 事件合约模拟系统启动",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    yield


app = FastAPI(
    title="事件合约模拟交易系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ───────────────────── 请求模型 ─────────────────────

class BacktestReq(BaseModel):
    symbol: str = "BTC_USDT"
    duration_hours: int = 4
    min_win_rate: float | None = None   # 最低胜率筛选，None=默认75%
    max_win_rate: float | None = None   # 最高胜率筛选，None=不过滤


class LockReq(BaseModel):
    duration: int
    strategy_id: str
    symbol: str = "BTC_USDT"


class ConfirmReq(BaseModel):
    action: str  # "resume" | "abort"

class SettingsReq(BaseModel):
    position_size: float | None = None


# ───────────────────── API 路由 ─────────────────────

@app.get("/")
def root():
    return {
        "service": "事件合约模拟交易系统",
        "version": "1.0.0",
        "status": app_state["status"],
    }


# ── 行情 ──

@app.get("/prices")
def get_prices():
    return {
        "prices": app_state["prices"],
        "status": app_state["status"],
        "data_source": get_data_source_info(),
    }


@app.get("/poll")
async def poll_all():
    """合并轮询：一次请求返回全部数据（价格+账户+持仓+事件），前端只需调这一个"""
    summary = get_position_summary()
    all_positions = get_open_positions() + get_closed_positions()[-30:]
    locked_info = {}
    for d, strats in app_state["locked"].items():
        locked_info[str(d)] = [
            {"id": s["id"], "name": s["name"], "symbol": s.get("symbol", "BTC_USDT")}
            for s in strats
        ]
    # 从 DB 聚合每策略 W/L（缓存 30 秒，只统计锁定后的交易）
    now = time.time()
    cached = app_state.get("_strategy_stats_cache")
    if not cached or now - cached.get("_ts", 0) > 30:
        sst = {}
        # 收集所有锁定策略的 locked_at 时间
        locked_since = {}
        for dur_str, strats in app_state["locked"].items():
            for s in strats:
                la = s.get("locked_at", "")
                key = f"{s['id']}_{dur_str}"
                locked_since[key] = la
        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT strategy_id, duration, pnl, entry_ts FROM sim_positions WHERE status='CLOSED' AND position_uid NOT LIKE 'obs_%'"
            )
            for row in await cursor.fetchall():
                sid, dur, pnl, entry_ts = row[0], row[1], row[2] or 0, row[3] or ""
                key = f"{sid}_{dur}"
                # 只统计锁定之后的交易
                since = locked_since.get(key, "")
                if since and entry_ts < since:
                    continue
                if key not in sst: sst[key] = {"wins": 0, "losses": 0}
                if pnl > 0: sst[key]["wins"] += 1
                else: sst[key]["losses"] += 1
        except Exception:
            sst = cached.get("_data", {}) if cached else {}
        app_state["_strategy_stats_cache"] = {"_ts": now, "_data": sst}
    strategy_stats = app_state["_strategy_stats_cache"]["_data"]
    return {
        "prices": app_state["prices"],
        "status": app_state["status"],
        "data_source": get_data_source_info(),
        "balance": summary["balance"],
        "open_count": summary["open_count"],
        "closed_count": summary["closed_count"],
        "win_rate": summary["win_rate"],
        "total_pnl": summary["total_pnl"],
        "wins": summary["wins"],
        "losses": summary["losses"],
        "position_size": app_state["position_size"],
        "locked": locked_info,
        "open_positions": get_open_positions(),
        "all_positions": all_positions,
        "strategy_stats": strategy_stats,
        "events": app_state["events"][-30:],
        "pending_confirm": app_state["pending_confirm"],
    }


@app.get("/datasource")
def datasource():
    return get_data_source_info()


@app.post("/datasource/reset")
def datasource_reset():
    import gate_client as gc
    old = gc._data_source
    gc._data_source = gc.SOURCE_LIVE
    for k in gc._fail_count:
        gc._fail_count[k] = 0
    app_state["events"].append({
        "level": "INFO",
        "msg": f"数据源已重置: {old} → LIVE",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {"source": gc._data_source, "previous": old}


@app.get("/prices/history")
async def get_price_history(
    symbol: str = Query("BTC_USDT"),
    hours: int = Query(1, ge=1, le=24),
):
    db = await get_db()
    cutoff = int(time.time()) - hours * 3600
    cursor = await db.execute(
        "SELECT price, ts FROM ticks WHERE symbol=? AND ts>=? ORDER BY ts ASC LIMIT 2000",
        (symbol, cutoff),
    )
    rows = await cursor.fetchall()
    return {
        "symbol": symbol,
        "data": [{"price": r[0], "ts": r[1]} for r in rows],
    }


# ── 回测 ──

@app.get("/reports")
def get_reports():
    return {
        "reports": app_state["last_reports"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# 回测缓存（同一参数30秒内不重复算）
_backtest_cache: dict = {}
_BT_CACHE_TTL = 30

@app.post("/backtest")
async def run_manual_backtest(req: BacktestReq):
    cache_key = f"{req.symbol}_{req.duration_hours}_{req.min_win_rate}_{req.max_win_rate}"
    now = time.time()
    if cache_key in _backtest_cache:
        cached_time, cached_result = _backtest_cache[cache_key]
        if now - cached_time < _BT_CACHE_TTL:
            return cached_result

    minute_window = req.duration_hours * 60
    try:
        from ext_gate import fetch_fine_bars
        df_15s, df_1m = await asyncio.gather(
            fetch_fine_bars(symbol=req.symbol, bar_seconds=15, minute_window=minute_window),
            fetch_candles(symbol=req.symbol, interval=CANDLE_INTERVAL, limit=minute_window),
        )
    except Exception as e:
        raise HTTPException(502, f"Gate.io API 请求失败: {e}")

    if (df_15s is None or df_15s.empty) and (df_1m is None or df_1m.empty):
        raise HTTPException(502, f"无法获取 {req.symbol} K 线数据")

    reports = evaluate_all_dual(df_15s, df_1m)

    # 自定义胜率筛选：>=min_win_rate OR <=max_win_rate（极端值）
    if req.min_win_rate is not None or req.max_win_rate is not None:
        min_wr = req.min_win_rate if req.min_win_rate is not None else 0.75
        max_wr = req.max_win_rate if req.max_win_rate is not None else 0.0
        reports = [r for r in reports if r["win_rate"] >= min_wr or r["win_rate"] <= max_wr]

    result = [{"symbol": req.symbol, "reports": reports}]
    app_state["last_reports"] = result

    app_state["events"].append({
        "level": "INFO",
        "msg": f"📊 手动回测 {req.symbol} × {req.duration_hours}h — {len(reports)} 条策略",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    _backtest_cache[cache_key] = (now, result)
    return result


@app.get("/strategies")
def list_strategies():
    clean = []
    for s in STRATEGIES:
        clean.append({"id": s["id"], "name": s["name"], "params": s["params"]})
    return {"strategies": clean, "durations": CONTRACT_DURATIONS}


# ── 策略锁定 ──

@app.post("/lock")
async def lock_strategy(req: LockReq):
    strat = next((s for s in STRATEGIES if s["id"] == req.strategy_id), None)
    if not strat:
        raise HTTPException(404, f"策略不存在: {req.strategy_id}")
    if req.duration not in CONTRACT_DURATIONS:
        raise HTTPException(400, f"合约时长错误，可选: {CONTRACT_DURATIONS}")
    if req.symbol not in SYMBOLS:
        raise HTTPException(400, f"品种错误，可选: {SYMBOLS}")

    existing = app_state["locked"][req.duration]
    for s in existing:
        if s["id"] == req.strategy_id and s.get("symbol") == req.symbol:
            raise HTTPException(400, f"该策略已锁定在 {req.symbol} {req.duration}m")

    entry = {**strat, "symbol": req.symbol, "locked_at": datetime.now(timezone.utc).isoformat()}
    existing.append(entry)
    app_state.pop("_strategy_stats_cache", None)  # 清缓存，让前端立刻看到新策略的 W/L
    app_state["events"].append({
        "level": "INFO",
        "msg": f"🔒 已锁定 {req.symbol} {req.duration}m: {strat['name']} ({strat['id']})",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    # 持久化
    try: await save_locked_strategies(app_state["locked"])
    except: pass
    return _locked_summary()


@app.post("/unlock")
async def unlock_strategy(duration: int = Query(...), strategy_id: str = Query(None)):
    if duration not in CONTRACT_DURATIONS:
        raise HTTPException(400, f"合约时长错误，可选: {CONTRACT_DURATIONS}")

    if strategy_id:
        before = len(app_state["locked"][duration])
        app_state["locked"][duration] = [
            s for s in app_state["locked"][duration]
            if s["id"] != strategy_id
        ]
        removed = before - len(app_state["locked"][duration])
        if removed == 0:
            raise HTTPException(404, f"未找到策略: {strategy_id}")
        app_state["events"].append({
            "level": "INFO",
            "msg": f"🔓 已解锁 {duration}m 策略: {strategy_id}",
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    else:
        count = len(app_state["locked"][duration])
        app_state["locked"][duration] = []
        app_state["events"].append({
            "level": "INFO",
            "msg": f"🔓 已清空 {duration}m 全部 {count} 条策略",
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    try: await save_locked_strategies(app_state["locked"])
    except: pass
    return _locked_summary()


def _locked_summary():
    summary = {}
    for d, strats in app_state["locked"].items():
        summary[str(d)] = [
            {"id": s["id"], "name": s["name"], "symbol": s.get("symbol", "BTC_USDT")}
            for s in strats
        ]
    return {"locked": summary}


# ── 系统控制 ──

@app.post("/control/pause")
def pause():
    app_state["status"] = "PAUSED"
    app_state["events"].append({
        "level": "WARN",
        "msg": "⏸️ 系统已暂停",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": app_state["status"]}


@app.post("/control/resume")
def resume():
    if app_state["pending_confirm"]:
        raise HTTPException(400, "存在待确认异常，请先调用 /control/confirm 处理")
    app_state["pending_confirm"] = None
    app_state["status"] = "RUNNING"
    app_state["events"].append({
        "level": "INFO",
        "msg": "▶️ 系统已恢复运行",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": app_state["status"]}


@app.post("/control/confirm")
def confirm(req: ConfirmReq):
    if not app_state["pending_confirm"]:
        return {"status": app_state["status"], "pending": None}

    if req.action == "resume":
        app_state["pending_confirm"] = None
        app_state["status"] = "RUNNING"
        msg = "✅ 异常已确认，系统恢复运行"
    elif req.action == "abort":
        app_state["pending_confirm"] = None
        app_state["status"] = "PAUSED"
        msg = "🛑 已中止，系统保持暂停"
    else:
        raise HTTPException(400, "action 必须是 resume 或 abort")

    app_state["events"].append({
        "level": "INFO",
        "msg": msg,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "status": app_state["status"],
        "pending": app_state["pending_confirm"],
    }


@app.get("/control/status")
def system_status():
    return {
        "status": app_state["status"],
        "pending_confirm": app_state["pending_confirm"],
        "prices": app_state["prices"],
        "locked": _locked_summary()["locked"],
    }


# ── 模拟账户 ──

@app.get("/account")
async def account():
    summary = get_position_summary()
    all_positions = get_open_positions() + get_closed_positions()[-30:]
    locked_info = {}
    for d, strats in app_state["locked"].items():
        locked_info[str(d)] = [
            {"id": s["id"], "name": s["name"], "symbol": s.get("symbol", "BTC_USDT")}
            for s in strats
        ]
    # 从 DB 聚合每策略 W/L（只统计锁定后的交易）
    strategy_stats = {}
    locked_since = {}
    for dur_str, strats in app_state["locked"].items():
        for s in strats:
            locked_since[f"{s['id']}_{dur_str}"] = s.get("locked_at", "")
    try:
        db = await get_db()
        cursor = await db.execute(
            "SELECT strategy_id, duration, pnl, entry_ts FROM sim_positions WHERE status='CLOSED' AND position_uid NOT LIKE 'obs_%'"
        )
        for row in await cursor.fetchall():
            sid, dur, pnl, entry_ts = row[0], row[1], row[2] or 0, row[3] or ""
            key = f"{sid}_{dur}"
            since = locked_since.get(key, "")
            if since and entry_ts < since:
                continue
            if key not in strategy_stats:
                strategy_stats[key] = {"wins": 0, "losses": 0}
            if pnl > 0: strategy_stats[key]["wins"] += 1
            else: strategy_stats[key]["losses"] += 1
    except Exception:
        pass
    return {
        **summary,
        "status": app_state["status"],
        "pending_confirm": app_state["pending_confirm"],
        "position_size": app_state["position_size"],
        "locked": locked_info,
        "open_positions": get_open_positions(),
        "all_positions": all_positions,
        "strategy_stats": strategy_stats,
        "events": app_state["events"][-50:],
    }


@app.get("/account/positions")
def account_positions(status: str = Query("all")):
    if status == "OPEN":
        return {"positions": get_open_positions()}
    elif status == "CLOSED":
        return {"positions": [
            p for p in app_state["open_positions"] if p["status"] == "CLOSED"
        ]}
    return {"positions": app_state["open_positions"]}


@app.get("/account/history")
async def account_history(limit: int = Query(50, ge=1, le=500)):
    db = await get_db()
    cursor = await db.execute(
        """SELECT position_uid, symbol, duration, strategy_id, direction,
                  entry_price, entry_ts, exit_price, exit_ts, status, pnl
           FROM sim_positions
           WHERE status = 'CLOSED'
           ORDER BY exit_ts DESC LIMIT ?""",
        (limit,),
    )
    rows = await cursor.fetchall()
    history = []
    for r in rows:
        history.append({
            "id": r[0],
            "symbol": r[1],
            "duration": r[2],
            "strategy_id": r[3],
            "direction": r[4],
            "entry_price": r[5],
            "entry_ts": r[6],
            "exit_price": r[7],
            "exit_ts": r[8],
            "status": r[9],
            "pnl": r[10],
        })
    mem_closed = [p for p in app_state["open_positions"] if p["status"] == "CLOSED"]
    mem_ids = {h["id"] for h in history}
    for p in mem_closed:
        if p["id"] not in mem_ids:
            history.append({
                "id": p["id"],
                "symbol": p["symbol"],
                "duration": p["duration"],
                "strategy_id": p["strategy_id"],
                "direction": p["direction"],
                "entry_price": p["entry_price"],
                "entry_ts": p["entry_ts"],
                "exit_price": p["exit_price"],
                "exit_ts": p["exit_ts"],
                "status": p["status"],
                "pnl": p["pnl"],
            })
    history.sort(key=lambda x: x.get("exit_ts", ""), reverse=True)
    return {"history": history[:limit], "total": len(history)}


# ── 设置 ──

@app.get("/settings")
def get_settings():
    return {
        "position_size": app_state["position_size"],
        "balance": app_state["balance"],
        "status": app_state["status"],
    }


@app.post("/settings")
def update_settings(req: SettingsReq):
    if req.position_size is not None:
        if req.position_size < 1 or req.position_size > 100000:
            raise HTTPException(400, "仓位金额需在 1 ~ 100000 USDT 之间")
        old = app_state["position_size"]
        app_state["position_size"] = req.position_size
        app_state["events"].append({
            "level": "INFO",
            "msg": f"⚙️ 仓位金额: ${old:.0f} → ${req.position_size:.0f}",
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    return {
        "position_size": app_state["position_size"],
        "balance": app_state["balance"],
    }


# ── 自动锁定 ──

@app.get("/auto-lock/status")
def auto_lock_status():
    al = app_state["auto_lock"]
    closed = get_closed_positions()
    stats = {}
    for d in CONTRACT_DURATIONS:
        dur_trades = [c for c in closed if c["duration"] == d and c.get("strategy_id")]
        total = len(dur_trades)
        wins = sum(1 for c in dur_trades if (c.get("pnl") or 0) > 0)
        stats[str(d)] = {
            "total": total, "wins": wins, "losses": total - wins,
            "win_rate": round(wins / total, 4) if total > 0 else 0,
            "total_pnl": round(sum(c.get("pnl") or 0 for c in dur_trades), 2),
        }
    return {
        "enabled": al["enabled"],
        "symbol": al["symbol"],
        "settings": {
            "backtest_hours": al.get("backtest_hours", [1, 2]),
            "win_rate_threshold": al.get("win_rate_threshold", 0.80),
            "min_trades": al.get("min_trades", 10),
            "loss_streak_enabled": al.get("loss_streak_enabled", True),
            "loss_streak_max": al.get("loss_streak_max", 2),
            "reverse_mode": al.get("reverse_mode", False),
        },
        "durations": {str(d): {
            "status": ds["status"], "active_strategy": ds["active_strategy"],
            "trade_count": ds["trade_count"], "win_count": ds["win_count"],
            "loss_streak": ds.get("loss_streak", 0), "last_trade_pnl": ds["last_trade_pnl"],
        } for d, ds in al["durations"].items()},
        "stats": stats,
    }


@app.post("/auto-lock/settings")
def auto_lock_settings(
    backtest_hours: str = Query(None),
    win_rate_threshold: float = Query(None),
    min_trades: int = Query(None),
    loss_streak_enabled: bool = Query(None),
    loss_streak_max: int = Query(None),
    reverse_mode: bool = Query(None),
):
    al = app_state["auto_lock"]
    if backtest_hours:
        al["backtest_hours"] = [int(h) for h in backtest_hours.split(",") if h.strip().isdigit()]
    if win_rate_threshold is not None:
        al["win_rate_threshold"] = max(0.0, min(1.0, win_rate_threshold))
    if min_trades is not None:
        al["min_trades"] = max(1, min(100, min_trades))
    if loss_streak_enabled is not None:
        al["loss_streak_enabled"] = loss_streak_enabled
    if loss_streak_max is not None:
        al["loss_streak_max"] = max(1, min(10, loss_streak_max))
    if reverse_mode is not None:
        al["reverse_mode"] = reverse_mode
    return {"ok": True, "settings": al.get("backtest_hours"), **auto_lock_status()}


@app.post("/auto-lock/start")
def auto_lock_start(symbol: str = Query("BTC_USDT"), durations: str = Query("3,5,10")):
    al = app_state["auto_lock"]
    al["enabled"] = True
    al["symbol"] = symbol
    # 解析选中的时长
    selected = [int(d) for d in durations.split(",") if int(d) in CONTRACT_DURATIONS]
    al["active_durations"] = selected
    for dur in CONTRACT_DURATIONS:
        ds = al["durations"][dur]
        if dur in selected:
            ds["status"] = "searching"
            ds["active_strategy"] = None
            ds["trade_count"] = 0
            ds["win_count"] = 0
        else:
            ds["status"] = "idle"
            ds["active_strategy"] = None
    app_state["events"].append({
        "level": "INFO",
        "msg": f"🤖 自动锁定开启: {symbol} {','.join(str(d)+'m' for d in selected)}",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, **auto_lock_status()}


@app.post("/auto-lock/stop")
def auto_lock_stop():
    al = app_state["auto_lock"]
    al["enabled"] = False
    for dur in CONTRACT_DURATIONS:
        app_state["locked"][dur] = [s for s in app_state["locked"][dur] if not s.get("_auto")]
        al["durations"][dur]["status"] = "idle"
        al["durations"][dur]["active_strategy"] = None
    app_state["events"].append({
        "level": "INFO",
        "msg": "🤖 自动锁定已关闭，自动策略已清空",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, **auto_lock_status()}


# ── 策略详情（溯源） ──

@app.get("/trace/{strategy_id}")
def trace_strategy(
    strategy_id: str,
    symbol: str = Query("BTC_USDT"),
    duration: int = Query(3),
):
    if not app_state["last_reports"]:
        raise HTTPException(404, "暂无回测报告，请先运行回测")

    for sym_reports in app_state["last_reports"]:
        if sym_reports["symbol"] != symbol:
            continue
        for rep in sym_reports["reports"]:
            if rep["strategy_id"] == strategy_id and rep["duration"] == duration:
                return rep

    raise HTTPException(404, f"未找到策略 {strategy_id} 在 {symbol} {duration}m 上的回测记录")


# ───────────────────── 入口 ─────────────────────

if __name__ == "__main__":
    import logging, uvicorn
    # 屏蔽 Windows 客户端断连导致的 WinError 64 日志噪音
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    uvicorn.run(app, host="0.0.0.0", port=8000)
