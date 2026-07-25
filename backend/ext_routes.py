"""
扩展 API 路由 — 观测池接口，挂载到原始 FastAPI app
"""
import asyncio
from fastapi import Query
from state import app_state
from observation_pool import init_observation_pool


def register_observation_routes(app):
    """在原始 app 上注册观测池路由和生命周期钩子。"""

    @app.get("/pool/stats")
    async def observation_pool_stats():
        pool = app_state.get("observation_pool", {})
        positions = pool.get("positions", [])
        stats = pool.get("stats", {})
        return {
            "stats": stats,
            "open_count": sum(1 for p in positions if p.get("status") == "OPEN"),
            "closed_count": sum(1 for p in positions if p.get("status") == "CLOSED"),
        }

    @app.post("/pool/init")
    async def observation_pool_init():
        init_observation_pool()
        return {"ok": True, "msg": "观测池已重新初始化"}
