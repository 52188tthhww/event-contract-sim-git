# 事件合约模拟交易系统

Gate.io 事件合约（3m/5m/10m）回测 + 策略筛选 + 模拟跟单系统。

## 架构

```
前端 React + Recharts  ←HTTP→  后端 FastAPI + asyncio  ←HTTPS→  Gate.io REST API
```

## 快速启动

### 1. 后端

```bash
cd backend
pip install -r requirements.txt
python main.py
# → http://localhost:8000
```

### 2. 前端

```bash
cd frontend
npm install
npm start
# → http://localhost:3000
```

## 功能

| 功能 | 说明 |
|------|------|
| BTC/ETH 实时行情图 | Gate.io 2s 轮询，Recharts 折线图 |
| 回测引擎 | 60s 自动回测 + 手动自定义回溯时长 |
| 策略库 | MA 交叉 ×5 + RSI 反转 ×4 + 布林带 ×4 = 13 条策略 |
| ≥75% 胜率筛选 | 自动高亮、排序、优先展示 |
| 策略溯源 | 每笔交易入场/出场时间、价格、方向、盈亏明细 + 散点图 |
| 策略锁定 | 人工核验后锁定，模拟交易员按策略自动开仓 |
| 异常暂停确认 | 异常时暂停系统，人工确认后恢复 |

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/prices` | GET | 最新价格 |
| `/backtest` | POST | 手动回测 |
| `/reports` | GET | 最近回测报告 |
| `/strategies` | GET | 策略列表 |
| `/lock` | POST | 锁定策略 |
| `/unlock` | POST | 解锁策略 |
| `/control/pause` | POST | 暂停 |
| `/control/resume` | POST | 恢复 |
| `/control/confirm` | POST | 确认异常 |
| `/account` | GET | 模拟账户 |
| `/trace/{id}` | GET | 策略溯源 |

## 策略

### MA 双均线交叉
- MA 3/10, 5/20, 5/30, 10/30, 10/50

### RSI 超买超卖反转
- RSI 7 (80/20), RSI 14 (70/30), RSI 14 (75/25), RSI 21 (70/30)

### 布林带突破
- BB 10/1.5, BB 20/2.0, BB 20/2.5, BB 30/2.0

## 免责声明

本系统为模拟/回测工具，不保证实盘盈利。接入实盘前请充分验证。
