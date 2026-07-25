"""
模拟交易员
- 开虚拟仓位
- 到期自动平仓
- 资金曲线跟踪
"""
import asyncio
from datetime import datetime, timezone
from state import app_state


def _now_iso() -> str:
    """当前 UTC 时间 ISO 字符串"""
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> float:
    """当前 UTC 时间戳"""
    return datetime.now(timezone.utc).timestamp()


async def open_position(
    symbol: str,
    duration: int,
    direction: int,
    price: float,
    strategy_id: str,
    strategy_name: str = "",
) -> dict | None:
    """
    开模拟仓位。
    返回持仓字典，如果已有同品种同时长持仓则返回 None。
    """
    # 检查是否已有同品种+同时长+同策略持仓（多策略并行不冲突）
    exists = any(
        p["symbol"] == symbol
        and p["duration"] == duration
        and p["strategy_id"] == strategy_id
        and p["status"] == "OPEN"
        for p in app_state["open_positions"]
    )
    if exists:
        return None

    dir_str = "UP" if direction == 1 else "DOWN"
    pos_size = app_state.get("position_size", 100.0)
    pos = {
        "id": f"{symbol}_{duration}_{_now_ts()}",
        "symbol": symbol,
        "duration": duration,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "direction": dir_str,
        "entry_price": price,
        "position_size": pos_size,
        "entry_ts": _now_iso(),
        "exit_price": None,
        "exit_ts": None,
        "status": "OPEN",
        "pnl": None,
    }

    app_state["open_positions"].append(pos)
    app_state["events"].append({
        "level": "INFO",
        "msg": f"📈 开仓 {symbol} {duration}m {dir_str} @ {price:.4f} 金额=${pos_size:.0f} [{strategy_name or strategy_id}]",
        "ts": _now_iso(),
    })

    # 异步到期平仓
    asyncio.create_task(_close_after_duration(pos))

    return pos


async def _close_after_duration(pos: dict):
    """等待合约到期后自动平仓"""
    await asyncio.sleep(pos["duration"] * 60)

    # 用标记价作为平仓价（和实盘结算价更接近）
    mark_prices = app_state.get("mark_prices", {})
    current_price = mark_prices.get(pos["symbol"], app_state["prices"].get(pos["symbol"], pos["entry_price"]))
    direction = 1 if pos["direction"] == "UP" else -1
    pos_size = pos.get("position_size", app_state.get("position_size", 100.0))
    # PnL = 涨跌幅% × 仓位金额 × 方向
    price_chg_pct = (current_price - pos["entry_price"]) / pos["entry_price"]
    pnl = price_chg_pct * pos_size * direction  # direction: UP=1, DOWN=-1

    pos["exit_price"] = current_price
    pos["exit_ts"] = _now_iso()
    pos["status"] = "CLOSED"
    pos["pnl"] = round(pnl, 4)
    pos["pnl_pct"] = round(price_chg_pct * 100 * direction, 4)  # 带方向的涨跌幅

    app_state["balance"] += pnl
    result_emoji = "WIN" if pnl > 0 else "LOSE"
    app_state["events"].append({
        "level": "INFO",
        "msg": (
            f"{'✅' if pnl > 0 else '❌'} 平仓 {pos['symbol']} {pos['duration']}m "
            f"{pos['direction']} @ {current_price:.4f} "
            f"PnL={pnl:+.2f}USDT | 余额={app_state['balance']:.2f}"
        ),
        "ts": _now_iso(),
    })

    # 持久化到 SQLite
    try:
        from db import get_db, save_position
        db = await get_db()
        await save_position(db, pos)
    except Exception:
        pass


def get_open_positions() -> list[dict]:
    """获取当前持仓"""
    return [p for p in app_state["open_positions"] if p["status"] == "OPEN"]


def get_closed_positions() -> list[dict]:
    """获取已平仓记录"""
    return [p for p in app_state["open_positions"] if p["status"] == "CLOSED"]


def get_position_summary() -> dict:
    """持仓统计摘要"""
    closed = get_closed_positions()
    open_pos = get_open_positions()
    total_closed = len(closed)
    wins = sum(1 for p in closed if (p.get("pnl") or 0) > 0)
    total_pnl = sum(p.get("pnl") or 0 for p in closed)

    return {
        "open_count": len(open_pos),
        "closed_count": total_closed,
        "wins": wins,
        "losses": total_closed - wins,
        "win_rate": round(wins / total_closed, 4) if total_closed > 0 else 0.0,
        "total_pnl": round(total_pnl, 4),
        "balance": round(app_state["balance"], 2),
    }
