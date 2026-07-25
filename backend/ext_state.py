"""
扩展状态 — 给 app_state 加 observation_pool，不修改原始 state.py
"""
from state import app_state


def extend_state():
    """挂载观测池到全局状态（幂等，重复调用不覆盖已有数据）"""
    if "observation_pool" not in app_state:
        app_state["observation_pool"] = {
            "positions": [],
            "stats": {},
        }
