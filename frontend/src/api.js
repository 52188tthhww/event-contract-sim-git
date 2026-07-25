import axios from 'axios';

const API = process.env.REACT_APP_API ?? '';

// 共享 axios 实例 — keep-alive + 超时 + 重试
const http = axios.create({
  baseURL: API,
  timeout: 120000,
  headers: {
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache',
  },
});

// 静默模式 — 轮询接口报错不打印到控制台
const silent = (fn) => fn().catch(() => null);

// GET 请求带 1 次重试
const getWithRetry = (url, opts = {}) =>
  http.get(url, opts).catch(() => http.get(url, opts));

// ═══════════════════════════════════════

// 行情
export const getPrices = () =>
  silent(() => getWithRetry('/prices').then(r => r.data));

// 合并轮询（价格+账户，一次请求）
export const pollAll = () =>
  silent(() => getWithRetry('/poll').then(r => r.data));

// 回测
export const getReports = () =>
  silent(() => http.get('/reports').then(r => r.data));

export const runBacktest = (payload) =>
  http.post('/backtest', payload, { timeout: 120000 }).then(r => r.data);

// 策略
export const getStrategies = () =>
  http.get('/strategies').then(r => r.data);

export const lockStrategy = (payload) =>
  http.post('/lock', payload).then(r => r.data);

export const unlockStrategy = (duration, strategyId) =>
  http.post('/unlock', null, { params: { duration, strategy_id: strategyId } }).then(r => r.data);

// 系统控制
export const control = (action, payload = {}) =>
  http.post(`/control/${action}`, payload).then(r => r.data);

export const systemStatus = () =>
  silent(() => http.get('/control/status').then(r => r.data));

// 账户
export const getAccount = () =>
  silent(() => getWithRetry('/account').then(r => r.data));

// 溯源
export const getTrace = (strategyId, symbol, duration) =>
  http.get(`/trace/${strategyId}`, { params: { symbol, duration } }).then(r => r.data);

// 设置
export const getSettings = () =>
  http.get('/settings').then(r => r.data);

export const updateSettings = (payload) =>
  http.post('/settings', payload).then(r => r.data);

// 历史记录
export const getHistory = (limit = 50) =>
  silent(() => http.get('/account/history', { params: { limit } }).then(r => r.data));

// 自动锁定
export const autoLockStatus = () =>
  http.get('/auto-lock/status').then(r => r.data);
export const autoLockStart = (durations, symbol = 'BTC_USDT') =>
  http.post('/auto-lock/start', null, { params: { symbol, durations: durations.join(',') } }).then(r => r.data);
export const autoLockStop = () =>
  http.post('/auto-lock/stop').then(r => r.data);
export const autoLockSettings = (params) =>
  http.post('/auto-lock/settings', null, { params }).then(r => r.data);
