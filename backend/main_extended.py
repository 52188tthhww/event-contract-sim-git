"""
事件合约模拟交易系统 — 扩展版入口
原始 main.py 保持不动，扩展层在此文件统一加载。
启动: python main_extended.py  (默认 :8001)
"""
import os, sys, asyncio, logging
from contextlib import asynccontextmanager

# ═══════════════════════════════════════════
# 1. 扩展状态
# ═══════════════════════════════════════════
from ext_state import extend_state
extend_state()

# ═══════════════════════════════════════════
# 2. 导入原始 main（不触发 uvicorn.run）
# ═══════════════════════════════════════════
import main as _main

# ═══════════════════════════════════════════
# 3. 扩展策略库
# ═══════════════════════════════════════════
from ext_strategies import extend_strategies
extend_strategies()

# ═══════════════════════════════════════════
# 4. 包装 lifespan：注入观测池后台循环
# ═══════════════════════════════════════════
from contextlib import asynccontextmanager as _acm

_original_lifespan = _main.lifespan

@_acm
async def _extended_lifespan(app):
    async with _original_lifespan(app):
        # 从 DB 恢复观测池历史统计
        from observation_pool import load_pool_stats
        await load_pool_stats()
        asyncio.ensure_future(_start_observation_loop())
        yield

# 直接替换 app 上已注册的 lifespan
_main.app.router.lifespan_context = _extended_lifespan


async def _start_observation_loop():
    from ext_config import OBS_SYMBOL, OBS_15S_MINUTE_WINDOW, OBS_1M_LIMIT, OBS_POLL_INTERVAL
    from gate_client import fetch_candles
    from ext_gate import fetch_fine_bars
    from observation_pool import run_observation_cycle
    from config import CANDLE_INTERVAL
    from state import app_state

    await asyncio.sleep(8)
    while True:
        await asyncio.sleep(OBS_POLL_INTERVAL)
        if app_state.get("status") != "RUNNING":
            continue
        try:
            price = app_state.get("prices", {}).get(OBS_SYMBOL)
            if price is None or price <= 0:
                continue
            df_15s, df_1m = await asyncio.gather(
                fetch_fine_bars(symbol=OBS_SYMBOL, bar_seconds=15, minute_window=OBS_15S_MINUTE_WINDOW),
                fetch_candles(symbol=OBS_SYMBOL, interval=CANDLE_INTERVAL, limit=OBS_1M_LIMIT),
            )
            await run_observation_cycle(OBS_SYMBOL, price, df_15s, df_1m)
        except Exception:
            pass


# ═══════════════════════════════════════════
# 5. 注册观测池路由
# ═══════════════════════════════════════════
from ext_routes import register_observation_routes
register_observation_routes(_main.app)

# ═══════════════════════════════════════════
# 6. 启动
# ═══════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BACKEND_PORT", "8001"))
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    print(f"扩展版启动: http://0.0.0.0:{port}")
    uvicorn.run(_main.app, host="0.0.0.0", port=port)
