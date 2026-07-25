"""
观测池 — 完全独立于 auto-lock trader
- 遍历全部策略，独立虚拟持仓
- 每策略×每时长最多 1 个 OPEN 持仓
- 按时长结算，统计每策略在各时长的胜率
"""
import time
from datetime import datetime, timezone
from state import app_state
from strategies import STRATEGIES
from config import CONTRACT_DURATIONS
from db import get_db  # 顶层导入，fail-fast


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


# ── 初始化 / 重置 ──

def init_observation_pool():
    """完全清空观测池数据（触发于 /pool/init）"""
    app_state["observation_pool"]["positions"].clear()
    app_state["observation_pool"]["stats"].clear()
    app_state["events"].append({
        "level": "INFO",
        "msg": "🔄 观测池已重新初始化",
        "ts": _now_iso(),
    })


# ── 统计辅助 ──

def _ensure_strategy_stats(strategy_id: str, strategy_name: str):
    """确保某策略的统计条目存在（惰性初始化）"""
    stats = app_state["observation_pool"]["stats"]
    if strategy_id not in stats:
        stats[strategy_id] = {
            "strategy_name": strategy_name,
            "3":  {"wins": 0, "losses": 0},
            "5":  {"wins": 0, "losses": 0},
            "10": {"wins": 0, "losses": 0},
        }


def _record_settlement(strategy_id: str, strategy_name: str, duration: int, is_win: bool):
    """结算一笔虚拟持仓，更新该策略在该时长的统计"""
    _ensure_strategy_stats(strategy_id, strategy_name)
    dk = str(duration)
    entry = app_state["observation_pool"]["stats"][strategy_id][dk]
    if is_win:
        entry["wins"] += 1
    else:
        entry["losses"] += 1


# ── 持仓结算 ──

def settle_expired_positions(price: float) -> list[dict]:
    """遍历所有 OPEN 持仓，对到期持仓按当前价格结算。
    返回本次新结算的持仓列表（供调用方持久化到 DB）。"""
    now = _now_ts()
    pool = app_state["observation_pool"]
    newly_closed = []

    for pos in pool["positions"]:
        if pos["status"] != "OPEN":
            continue

        # 持仓到期时间 = 入场时间 + duration(分钟)
        try:
            entry_ts = datetime.fromisoformat(pos["entry_time"]).timestamp()
        except (ValueError, TypeError, KeyError):
            # 损坏的 entry_time：累计失败次数，超阈值强制结算以防永久泄漏
            pos.setdefault("_bad_parse", 0)
            pos["_bad_parse"] += 1
            if pos["_bad_parse"] >= 10:
                pos["exit_price"] = price
                pos["exit_time"] = _now_iso()
                pos["status"] = "CLOSED"
                pos["pnl"] = 0.0
                newly_closed.append(pos)
            continue
        expire_ts = entry_ts + pos["duration"] * 60
        if now < expire_ts:
            continue

        # 结算
        direction = pos["direction"]
        pnl = (price - pos["entry_price"]) * direction
        is_win = pnl > 0

        pos["exit_price"] = price
        pos["exit_time"] = _now_iso()
        pos["status"] = "CLOSED"
        pos["pnl"] = round(pnl, 4)

        _record_settlement(
            pos["strategy_id"], pos["strategy_name"],
            pos["duration"], is_win,
        )
        newly_closed.append(pos)

    if newly_closed:
        app_state["events"].append({
            "level": "INFO",
            "msg": f"🔍 观测池结算 {len(newly_closed)} 笔持仓",
            "ts": _now_iso(),
        })

    # 定期清理旧 CLOSED 持仓，防止内存无限增长
    MAX_CLOSED = 3000
    closed_positions = [p for p in pool["positions"] if p["status"] == "CLOSED"]
    if len(closed_positions) > MAX_CLOSED:
        closed_positions.sort(
            key=lambda p: p.get("exit_time", ""), reverse=True
        )
        keep_ids = {p["id"] for p in closed_positions[:MAX_CLOSED]}
        pool["positions"] = [
            p for p in pool["positions"]
            if p["status"] == "OPEN" or p["id"] in keep_ids
        ]

    return newly_closed


# ── 开仓 ──

def open_observation_position(
    symbol: str, duration: int, direction: int, price: float,
    strategy_id: str, strategy_name: str,
) -> bool:
    """开观测池虚拟持仓。返回 True 表示开仓成功，False 表示已有同策略同时长持仓。"""
    if direction not in (1, -1):
        return False
    pool = app_state["observation_pool"]

    # 检查是否已有同策略 + 同时长 + OPEN 持仓
    exists = any(
        p["strategy_id"] == strategy_id
        and p["duration"] == duration
        and p["status"] == "OPEN"
        for p in pool["positions"]
    )
    if exists:
        return False

    pos = {
        "id": f"obs_{symbol}_{duration}_{strategy_id}_{int(_now_ts())}",
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "symbol": symbol,
        "duration": duration,
        "direction": direction,  # 1 or -1
        "entry_price": price,
        "entry_time": _now_iso(),
        "exit_price": None,
        "exit_time": None,
        "status": "OPEN",
        "pnl": None,
    }
    pool["positions"].append(pos)

    # 惰性初始化该策略统计
    _ensure_strategy_stats(strategy_id, strategy_name)

    return True


# ── DB 持久化 ──

async def _persist_closed_positions(positions: list[dict]):
    """将已平仓持仓写入 SQLite，与回测/历史记录共用数据库。"""
    try:
        db = await get_db()
        for pos in positions:
            db_pos = dict(pos)
            if isinstance(db_pos.get("direction"), int):
                db_pos["direction"] = "UP" if db_pos["direction"] == 1 else "DOWN"
            db_pos["entry_ts"] = db_pos.pop("entry_time", db_pos.get("entry_ts"))
            db_pos["exit_ts"] = db_pos.pop("exit_time", db_pos.get("exit_ts"))
            await save_position(db, db_pos)
    except Exception:
        # DB 不可用时静默降级，首次记录到事件日志
        if not app_state["observation_pool"].get("_db_fail_logged"):
            app_state["observation_pool"]["_db_fail_logged"] = True
            app_state["events"].append({
                "level": "WARN",
                "msg": "⚠️ 观测池 DB 持久化失败，持仓记录仅存内存",
                "ts": _now_iso(),
            })


async def save_pool_stats():
    """持久化观测池统计到 DB（首次自动建表）。"""
    try:
        import json
        db = await get_db()
        await db.execute("CREATE TABLE IF NOT EXISTS obs_pool_stats (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        stats_json = json.dumps(app_state["observation_pool"]["stats"], ensure_ascii=False)
        await db.execute(
            "INSERT OR REPLACE INTO obs_pool_stats(key, value) VALUES ('stats', ?)",
            (stats_json,),
        )
        await db.commit()
    except Exception:
        pass


async def load_pool_stats():
    """从 DB 恢复观测池统计。"""
    try:
        import json
        db = await get_db()
        cursor = await db.execute("SELECT value FROM obs_pool_stats WHERE key = 'stats'")
        row = await cursor.fetchone()
        if row and row[0]:
            app_state["observation_pool"]["stats"] = json.loads(row[0])
    except Exception:
        pass  # 首次启动表为空，或数据损坏，从零开始


# ── 主循环 ──

async def run_observation_cycle(
    symbol: str, price: float, df_15s, df_1m,
):
    """
    每 2 秒执行一次，由 main.py 的 observation_loop 调用。

    参数:
        symbol: 交易品种
        price:  当前实时价格（WebSocket）
        df_15s: 15s K 线 DataFrame — 3min 合约信号用
        df_1m:  1m K 线 DataFrame  — 5/10min 合约信号用
    """
    # ① 结算到期持仓
    newly_closed = settle_expired_positions(price)

    # ② 持久化观测池统计（不写入 sim_positions，观测池独立于历史交易记录）
    if newly_closed:
        await save_pool_stats()

    # ③ 按合约时长选 K 线粒度 + shift(1) + 算信号
    from ext_strategies import is_flip_strategy

    def _get_signal(st: dict, df_raw, dur_key: str) -> int:
        """对指定 DF 计算策略信号（统一 shift(1)），持续信号策略仅翻转时开仓。"""
        if df_raw is None or df_raw.empty or len(df_raw) < 10:
            return 0
        try:
            df_sig = st["fn"](df_raw.copy(), st["params"])
            shifted = df_sig["signal"].shift(1).fillna(0).astype(int)
            sig = int(shifted.iloc[-1])
        except Exception as e:
            _err_key = f"_err_{st['id']}"
            if _err_key not in app_state["observation_pool"]:
                app_state["observation_pool"][_err_key] = True
                app_state["events"].append({
                    "level": "WARN",
                    "msg": f"⚠️ 观测池策略 {st['id']} 信号计算异常: {e}",
                    "ts": _now_iso(),
                })
            return 0

        # 翻转限制：信号方向与上次相同则不开仓
        if is_flip_strategy(st["id"]):
            prev_key = f"_ps_{st['id']}_{dur_key}"
            prev = app_state["observation_pool"].get(prev_key, 0)
            if sig == prev:
                return 0
            app_state["observation_pool"][prev_key] = sig
            # 5/10min 加量确认（dur_key=="5"或"10"，对应 1m DF）
            if dur_key in ("5", "10"):
                vol_ma = df_raw["volume"].rolling(20).mean()
                if df_raw["volume"].iloc[-1] <= vol_ma.iloc[-1]:
                    return 0
        return sig

    for st in STRATEGIES:
        # 3min → 15s K 线
        sig_3 = _get_signal(st, df_15s, "3")
        if sig_3 != 0:
            open_observation_position(symbol, 3, sig_3, price, st["id"], st["name"])

        # 5min / 10min → 1m K 线（各自独立 prev_sig，避免10min信号丢失）
        sig_5 = _get_signal(st, df_1m, "5")
        if sig_5 != 0:
            open_observation_position(symbol, 5, sig_5, price, st["id"], st["name"])
        sig_10 = _get_signal(st, df_1m, "10")
        if sig_10 != 0:
            open_observation_position(symbol, 10, sig_10, price, st["id"], st["name"])
