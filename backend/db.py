"""
SQLite 数据库初始化与操作
"""
import aiosqlite
from config import DB_PATH


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """初始化数据库表"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                ts INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticks_symbol_ts ON ticks(symbol, ts)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                duration INTEGER NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                win_rate REAL NOT NULL,
                total_trades INTEGER NOT NULL,
                wins INTEGER NOT NULL,
                net_pnl REAL NOT NULL,
                expectancy REAL NOT NULL,
                qualified INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sim_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_uid TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                duration INTEGER NOT NULL,
                strategy_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_ts TEXT NOT NULL,
                exit_price REAL,
                exit_ts TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                pnl REAL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                msg TEXT NOT NULL,
                ts TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS locked_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                duration INTEGER NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                symbol TEXT NOT NULL DEFAULT 'BTC_USDT',
                is_auto INTEGER NOT NULL DEFAULT 0
            )
        """)

        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.commit()


async def save_tick(db: aiosqlite.Connection, symbol: str, price: float, ts: int):
    """保存价格 tick"""
    await db.execute(
        "INSERT INTO ticks(symbol, price, ts) VALUES (?, ?, ?)",
        (symbol, price, ts),
    )
    await db.commit()


async def save_report(db: aiosqlite.Connection, symbol: str, report: dict):
    """保存回测报告"""
    import time
    await db.execute(
        """INSERT INTO backtest_reports
           (symbol, duration, strategy_id, strategy_name, win_rate,
            total_trades, wins, net_pnl, expectancy, qualified, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            symbol,
            report["duration"],
            report["strategy_id"],
            report["strategy_name"],
            report["win_rate"],
            report["total_trades"],
            report["wins"],
            report["net_pnl"],
            report["expectancy"],
            1 if report["qualified"] else 0,
            int(time.time()),
        ),
    )
    await db.commit()


async def save_position(db: aiosqlite.Connection, pos: dict):
    """保存模拟持仓"""
    await db.execute(
        """INSERT OR REPLACE INTO sim_positions
           (position_uid, symbol, duration, strategy_id, direction,
            entry_price, entry_ts, exit_price, exit_ts, status, pnl)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pos["id"],
            pos["symbol"],
            pos["duration"],
            pos["strategy_id"],
            pos["direction"],
            pos["entry_price"],
            pos["entry_ts"],
            pos.get("exit_price"),
            pos.get("exit_ts"),
            pos["status"],
            pos.get("pnl"),
        ),
    )
    await db.commit()


async def save_event(db: aiosqlite.Connection, level: str, msg: str, ts: str):
    """保存事件日志"""
    await db.execute(
        "INSERT INTO events(level, msg, ts) VALUES (?, ?, ?)",
        (level, msg, ts),
    )
    await db.commit()


async def save_locked_strategies(locked: dict):
    """持久化锁定策略到 SQLite"""
    db = await get_db()
    await db.execute("DELETE FROM locked_strategies")
    for dur, strats in locked.items():
        for s in strats:
            await db.execute(
                "INSERT INTO locked_strategies (duration, strategy_id, strategy_name, symbol, is_auto) VALUES (?, ?, ?, ?, ?)",
                (dur, s.get("id"), s.get("name"), s.get("symbol", "BTC_USDT"), 1 if s.get("_auto") else 0),
            )
    await db.commit()


async def load_locked_strategies(strategies_lookup: dict = None):
    """从 SQLite 恢复锁定策略"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM locked_strategies")
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "duration": r[1],
                "strategy_id": r[2],
                "name": r[3],
                "symbol": r[4],
                "_auto": bool(r[5]),
            })
        return result
    except Exception:
        return []
