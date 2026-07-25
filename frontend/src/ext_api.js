/**
 * 扩展 API — 观测池接口，不修改原始 api.js
 */
import axios from 'axios';

const API = process.env.REACT_APP_API ?? '';
const http = axios.create({ baseURL: API, timeout: 120000 });

const silent = (fn) => fn().catch(() => null);

// 观测池
export const getPoolStats = () =>
  silent(() => http.get('/pool/stats').then(r => r.data));
export const resetPool = () =>
  http.post('/pool/init').then(r => r.data);

// 策略锁定（复用原始 API 路径）
export const lockStrategy = (payload) =>
  http.post('/lock', payload).then(r => r.data);
export const unlockStrategy = (duration, strategyId, symbol = 'BTC_USDT') =>
  http.post('/unlock', null, { params: { duration, strategy_id: strategyId, symbol } }).then(r => r.data);
