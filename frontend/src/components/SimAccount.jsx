import React, { useEffect, useState, useCallback, useMemo, memo } from 'react';
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import { pollAll, control, updateSettings, unlockStrategy, getHistory, autoLockStart, autoLockStop, autoLockStatus, autoLockSettings } from '../api';
import ObservationPool from './ObservationPool';
import axios from 'axios';

const API = process.env.REACT_APP_API ?? '';
const histHttp = axios.create({ baseURL: API, timeout: 30000 });

const COLORS = { BTC_USDT: 'var(--text)', ETH_USDT: 'var(--text-secondary)' };
const LABELS = { BTC_USDT: 'BTC/USDT', ETH_USDT: 'ETH/USDT' };

// ── Web Audio 提示音 ──
let _audioCtx = null;
function getAudioCtx() {
  if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  return _audioCtx;
}
function playBeep(type = 'open') {
  try {
    const ctx = getAudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    // 开仓: 上升双音; 平仓盈: 高音; 平仓亏: 低音
    if (type === 'open') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(800, ctx.currentTime);
      osc.frequency.linearRampToValueAtTime(1200, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.25);
    } else if (type === 'win') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(1000, ctx.currentTime);
      osc.frequency.setValueAtTime(1400, ctx.currentTime + 0.08);
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.2);
    } else {
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(400, ctx.currentTime);
      osc.frequency.linearRampToValueAtTime(200, ctx.currentTime + 0.3);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.35);
    }
  } catch (_) { /* 浏览器不支持 */ }
}

export default function SimAccount() {
  const [acc, setAcc] = useState(null);
  const [message, setMessage] = useState('');
  // 价格历史
  const [priceData, setPriceData] = useState([]);
  // 所有持仓标记（OPEN + 最近 CLOSED）
  const [allPositions, setAllPositions] = useState([]);
  // 历史交易记录
  const [history, setHistory] = useState([]);
  // 自动锁定状态
  const [autoLock, setAutoLock] = useState({ enabled: false, durations: {} });
  const [autoLockSelected, setAutoLockSelected] = useState([3, 5, 10]);
  // 本地设置草稿（不立即调API，开启时才提交）
  const [localSettings, setLocalSettings] = useState({
    backtest_hours: '1,2', win_rate_threshold: 0.80, min_trades: 10,
    loss_streak_enabled: true, loss_streak_max: 2, reverse_mode: false,
  });
  // 提示音开关
  const [soundOn, setSoundOn] = useState(() => {
    return localStorage.getItem('sim_sound') !== 'off';
  });
  // 之前持仓数（用于检测新开仓/新平仓）
  const prevOpenRef = React.useRef(0);
  const prevClosedRef = React.useRef(0);
  const prevPosIds = React.useRef(new Set());
  const soundOnRef = React.useRef(soundOn);
  soundOnRef.current = soundOn;  // 实时同步，callback 里用 ref 读最新值
  // Toast 通知队列
  const [toasts, setToasts] = useState([]);
  const toastIdRef = React.useRef(0);

  const addToast = useCallback((type, data) => {
    const id = ++toastIdRef.current;
    setToasts(prev => [...prev.slice(-4), { id, type, data, ts: Date.now() }]);
    // 6 秒后自动移除
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 6000);
  }, []);

  // ── 数据轮询（单请求）──
  const refresh = useCallback(async () => {
    try {
      const data = await pollAll();
      if (!data) return;

      const prices = data.prices || {};
      const now = Date.now();
      setPriceData(prev => {
        const last = prev.length > 0 ? prev[prev.length - 1] : {};
        const btc = prices.BTC_USDT || last.BTC_USDT;
        const eth = prices.ETH_USDT || last.ETH_USDT;
        if (!btc && !eth) return prev;
        return [...prev, { time: now, BTC_USDT: btc, ETH_USDT: eth }].slice(-300);
      });

      setAcc(data);
      setAllPositions(data.all_positions || []);

      const closedNow = data.closed_count || 0;
      if (closedNow !== prevClosedRef.current) {
        try { const h = await getHistory(50); setHistory(h.history || []); } catch (_) {}
      }

      const openCount = data.open_count || 0;
      const closedCount = data.closed_count || 0;
      const allPos = data.all_positions || [];

      if (openCount > prevOpenRef.current) {
        if (soundOnRef.current) playBeep('open');
        const currentIds = new Set(allPos.filter(p => p.status === 'OPEN').map(p => p.id));
        for (const id of currentIds) {
          if (!prevPosIds.current.has(id)) {
            const pos = allPos.find(p => p.id === id);
            if (pos) addToast('open', pos);
          }
        }
      }
      if (closedCount > prevClosedRef.current) {
        const closedPositions = allPos.filter(p => p.status === 'CLOSED');
        const lastClosed = closedPositions[closedPositions.length - 1];
        if (soundOnRef.current) playBeep(lastClosed && (lastClosed.pnl || 0) > 0 ? 'win' : 'lose');
        if (lastClosed && !prevPosIds.current.has('closed_' + lastClosed.id)) {
          prevPosIds.current.add('closed_' + lastClosed.id);
          addToast('close', lastClosed);
        }
      }

      prevOpenRef.current = openCount;
      prevClosedRef.current = closedCount;
      prevPosIds.current = new Set(allPos.filter(p => p.status === 'OPEN').map(p => p.id));
    } catch (_) {}

    // 自动锁定状态
    try {
      const al = await autoLockStatus();
      setAutoLock(al);
    } catch (_) {}
  }, []);

  // 首次加载：后台拉取价格历史（不阻塞实时轮询）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [btcRes, ethRes] = await Promise.all([
          histHttp.get('/prices/history', { params: { symbol: 'BTC_USDT', hours: 1 } }),
          histHttp.get('/prices/history', { params: { symbol: 'ETH_USDT', hours: 1 } }),
        ]);
        if (cancelled) return;
        const btcH = (btcRes.data.data || []).map(p => ({ time: p.ts * 1000, BTC_USDT: p.price }));
        const ethH = (ethRes.data.data || []).map(p => ({ time: p.ts * 1000, ETH_USDT: p.price }));
        const merged = [];
        let bi = 0, ei = 0;
        while (bi < btcH.length || ei < ethH.length) {
          const bt = btcH[bi], et = ethH[ei];
          if (!bt) { merged.push(et); ei++; }
          else if (!et) { merged.push(bt); bi++; }
          else if (bt.time <= et.time) {
            merged.push({ ...bt, ETH_USDT: et.ETH_USDT });
            bi++; if (bt.time === et.time) ei++;
          } else { merged.push({ ...et, BTC_USDT: bt.BTC_USDT }); ei++; }
        }
        if (!cancelled) setPriceData(prev => {
          const prevTimes = new Set(prev.map(p => p.time));
          const newData = merged.filter(p => !prevTimes.has(p.time));
          return [...prev, ...newData].sort((a, b) => a.time - b.time).slice(-300);
        });
      } catch (_) {}
    })();
    return () => { cancelled = true; };
  }, []);

  // 实时轮询（立刻开始，不等待历史）
  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 3000);
    return () => clearInterval(iv);
  }, [refresh]);

  // 首次加载拉取 DB 历史（refresh 里只在平仓变化时拉）
  useEffect(() => {
    getHistory(50).then(h => setHistory(h.history || [])).catch(() => {});
  }, []);

  // ── 控制 ──
  const handleControl = async (action) => {
    setMessage('');
    try {
      const res = await control(action);
      setMessage(`操作成功 → 状态: ${res.status}`);
      refresh();
    } catch (e) {
      setMessage(`操作失败: ${e.response?.data?.detail || e.message}`);
    }
  };

  const handleConfirm = async (action) => {
    setMessage('');
    try {
      await control('confirm', { action });
      setMessage(action === 'resume' ? '已确认并恢复' : '已中止并暂停');
      refresh();
    } catch (e) {
      setMessage(`确认失败: ${e.response?.data?.detail || e.message}`);
    }
  };

  if (!acc) {
    return <div style={styles.empty}>⏳ 等待后端连接...</div>;
  }

  // ── 图表数据准备 ──
  const buildEntryMarkers = (symbol) => {
    return allPositions
      .filter(p => p.symbol === symbol)
      .map(p => ({
        time: new Date(p.entry_ts).getTime(),
        price: p.entry_price,
        direction: p.direction,
        duration: p.duration,
        status: p.status,
        strategy: p.strategy_name || p.strategy_id,
        id: p.id,
      }));
  };

  const btcMarkers = buildEntryMarkers('BTC_USDT');
  const ethMarkers = buildEntryMarkers('ETH_USDT');

  // 持仓 Y 轴参考线（当前持仓的入场价）
  const openBTCEntries = allPositions.filter(p => p.symbol === 'BTC_USDT' && p.status === 'OPEN');
  const openETHEntries = allPositions.filter(p => p.symbol === 'ETH_USDT' && p.status === 'OPEN');

  const statusColor = acc.status === 'RUNNING' ? 'var(--text)' : 'var(--text-secondary)';
  const formatPrice = (v) => v?.toFixed?.(2) || '—';
  const formatTime = (ts) => new Date(ts).toLocaleTimeString();
  // ISO/时间戳 → 本地时间字符串
  const toLocal = (isoOrTs) => {
    if (!isoOrTs) return '—';
    const d = new Date(isoOrTs);
    if (isNaN(d.getTime())) return isoOrTs;
    return d.toLocaleString();
  };
  const toLocalShort = (isoOrTs) => {
    if (!isoOrTs) return '—';
    const d = new Date(isoOrTs);
    if (isNaN(d.getTime())) return isoOrTs;
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return `${mm}-${dd} ${hh}:${min}:${ss}`;
  };

  const tooltipStyle = {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text)',
  };

  return (
    <div>
      {/* ═══════ Toast 通知层 ═══════ */}
      <div style={styles.toastLayer}>
        {toasts.map(t => (
          <div key={t.id} style={{
            ...styles.toast,
            ...(t.type === 'open' ? styles.toastOpen : {}),
            ...(t.type === 'close' && (t.data.pnl || 0) > 0 ? styles.toastWin : {}),
            ...(t.type === 'close' && (t.data.pnl || 0) <= 0 ? styles.toastLose : {}),
          }}>
            {t.type === 'open' ? (
              <>
                <span style={{ fontSize: 18 }}>
                  {t.data.direction === 'UP' ? '📈' : '📉'}
                </span>
                <div>
                  <div style={{ fontWeight: 700 }}>
                    开仓 {t.data.symbol} {t.data.duration}m {t.data.direction}
                  </div>
                  <div style={{ fontSize: 11, opacity: 0.8 }}>
                    @ {t.data.entry_price?.toFixed(2)} | 金额 ${t.data.position_size || '—'}
                  </div>
                </div>
              </>
            ) : (
              <>
                <span style={{ fontSize: 18 }}>
                  {(t.data.pnl || 0) > 0 ? '✅' : '❌'}
                </span>
                <div>
                  <div style={{ fontWeight: 700 }}>
                    平仓 {t.data.symbol} {t.data.duration}m {t.data.direction}
                  </div>
                  <div style={{ fontSize: 11, opacity: 0.8 }}>
                    盈亏: {(t.data.pnl || 0) >= 0 ? '+' : ''}{t.data.pnl?.toFixed(2)} USDT
                    {' '}({(t.data.pnl_pct || 0) >= 0 ? '+' : ''}{t.data.pnl_pct?.toFixed(3)}%)
                  </div>
                </div>
              </>
            )}
            <button
              onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
              style={styles.toastClose}
            >✕</button>
          </div>
        ))}
      </div>

      {/* ═══════ 异常确认弹窗 ═══════ */}
      {acc.pending_confirm && (
        <div style={styles.alert}>
          <div style={styles.alertIcon}>⚠️</div>
          <div style={styles.alertBody}>
            <div style={styles.alertTitle}>系统异常，需要确认</div>
            <div style={styles.alertMsg}>{acc.pending_confirm}</div>
            <div style={styles.alertActions}>
              <button onClick={() => handleConfirm('resume')} style={styles.confirmBtn}>
                确认并继续
              </button>
              <button onClick={() => handleConfirm('abort')} style={styles.abortBtn}>
                暂停系统
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════ 顶部指标栏 ═══════ */}
      <div style={styles.overviewGrid}>
        <div style={styles.card}>
          <div style={styles.cardLabel}>系统状态</div>
          <div style={{ ...styles.cardValue, color: statusColor }}>
            {acc.status === 'RUNNING' ? '▶ 运行中' : '⏸ 已暂停'}
          </div>
        </div>
        <div style={styles.card}>
          <div style={styles.cardLabel}>账户余额</div>
          <div style={styles.cardValue}>${acc.balance?.toFixed(2) || '—'}</div>
        </div>
        <div style={styles.card}>
          <div style={styles.cardLabel}>当前持仓</div>
          <div style={styles.cardValue}>{acc.open_count || 0} 个</div>
        </div>
        <div style={styles.card}>
          <div style={styles.cardLabel}>已平仓</div>
          <div style={styles.cardValue}>{acc.closed_count || 0} 笔</div>
        </div>
        <div style={styles.card}>
          <div style={styles.cardLabel}>胜率</div>
          <div style={{ ...styles.cardValue, color: (acc.win_rate || 0) >= 0.5 ? 'var(--text)' : 'var(--down)' }}>
            {((acc.win_rate || 0) * 100).toFixed(1)}%
          </div>
        </div>
        <div style={styles.card}>
          <div style={styles.cardLabel}>累计盈亏</div>
          <div style={{ ...styles.cardValue, color: (acc.total_pnl || 0) >= 0 ? 'var(--text)' : 'var(--down)' }}>
            {(acc.total_pnl || 0) >= 0 ? '+' : ''}{acc.total_pnl?.toFixed(4) || '0'}
          </div>
        </div>
      </div>

      {/* ═══════ 行情图 + 开仓标记 ═══════ */}
      <div style={styles.chartsGrid}>
        {['BTC_USDT', 'ETH_USDT'].map(sym => {
          const markers = sym === 'BTC_USDT' ? btcMarkers : ethMarkers;
          const opens = sym === 'BTC_USDT' ? openBTCEntries : openETHEntries;

          return (
            <div key={sym} style={styles.chartBox}>
              <div style={styles.chartHeader}>
                <h3 style={{ ...styles.chartTitle, color: COLORS[sym] }}>{LABELS[sym]}</h3>
                <span style={styles.chartBadge}>
                  {markers.length} 笔标记
                </span>
              </div>
              <ResponsiveContainer width="100%" height={320}>
                <ComposedChart data={priceData} margin={{ top: 10, right: 10, bottom: 5, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
                  <XAxis
                    dataKey="time"
                    tickFormatter={formatTime}
                    stroke="#484f58"
                    fontSize={10}
                  />
                  <YAxis
                    domain={(() => {
                      const vals = priceData.map(d => d[sym]).filter(v => v != null);
                      if (vals.length < 2) return ['auto', 'auto'];
                      const min = Math.min(...vals);
                      const max = Math.max(...vals);
                      const pad = (max - min) * 0.15 || max * 0.002;
                      return [Math.floor(min - pad), Math.ceil(max + pad)];
                    })()}
                    stroke="#484f58"
                    fontSize={10}
                    tickFormatter={v => v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v.toFixed(0)}
                    width={55}
                    allowDataOverflow
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelFormatter={formatTime}
                    formatter={(val, name) => {
                      if (name === LABELS[sym]) return ['$' + formatPrice(val), LABELS[sym]];
                      return [val, name];
                    }}
                  />
                  {/* 价格线 + 开仓标记点 */}
                  <Line
                    type="monotone"
                    dataKey={sym}
                    name={LABELS[sym]}
                    stroke={COLORS[sym]}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                  {/* 开仓标记 — 用 ReferenceLine 标注入场价 */}
                  {markers.slice(-10).map(m => (
                    <ReferenceLine
                      key={m.id}
                      y={m.price}
                      stroke={m.direction === 'UP' ? 'var(--text)' : 'var(--down)'}
                      strokeDasharray={m.status === 'OPEN' ? '2 2' : '6 3'}
                      strokeWidth={m.status === 'OPEN' ? 1.5 : 0.8}
                      opacity={m.status === 'OPEN' ? 1 : 0.5}
                      label={{
                        value: `${m.direction === 'UP' ? '▲' : '▼'} ${m.duration}m`,
                        fill: m.direction === 'UP' ? 'var(--text)' : 'var(--down)',
                        fontSize: 9,
                        position: 'right',
                      }}
                    />
                  ))}
                </ComposedChart>
              </ResponsiveContainer>
              {/* 最近标记列表 */}
              {markers.length > 0 && (
                <div style={styles.markerList}>
                  {markers.slice(-5).reverse().map(m => (
                    <span key={m.id} style={{
                      ...styles.markerTag,
                      color: m.direction === 'UP' ? 'var(--text)' : 'var(--down)',
                      borderColor: m.status === 'OPEN' ? (m.direction === 'UP' ? 'var(--text)' : 'var(--down)') : 'var(--border-light)',
                      background: m.status === 'OPEN'
                        ? (m.direction === 'UP' ? 'var(--accent-dim)' : 'rgba(255,255,255,.02)')
                        : 'transparent',
                    }}>
                      {m.direction === 'UP' ? '▲' : '▼'} {m.duration}m
                      @{m.price?.toFixed(1)}
                      {m.status === 'OPEN' && ' ●'}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ═══════ 锁定策略 + 控制 + 设置 ═══════ */}
      <div style={styles.controlPanel}>
        {/* 锁定策略 */}
        <div style={styles.controlBlock}>
          <h3 style={styles.sectionTitle}>🔒 已锁定策略</h3>
          <div style={styles.lockedGrid}>
            {acc.locked && Object.entries(acc.locked).map(([dur, list]) => {
              const strategies = Array.isArray(list) ? list : [];
              return (
              <div key={dur} style={{
                ...styles.lockedCard,
                borderColor: strategies.length > 0 ? 'var(--accent-dim)' : 'var(--surface-hover)',
              }}>
                <div style={styles.lockedDur}>{dur} 分钟</div>
                {strategies.length === 0 ? (
                  <div style={{ ...styles.lockedName, color: 'var(--text-secondary)' }}>未锁定</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {strategies.map((s, i) => {
                      const key = `${s.id}_${dur}`;
                      const st = (acc.strategy_stats || {})[key] || { wins: 0, losses: 0 };
                      const wins = st.wins || 0;
                      const losses = st.losses || 0;
                      const total = wins + losses;
                      return (
                      <div key={i} style={styles.lockedItem}>
                        <span style={{
                          ...styles.symBadge,
                          color: (s.symbol || 'BTC_USDT') === 'BTC_USDT' ? 'var(--text)' : 'var(--text-secondary)',
                          background: (s.symbol || 'BTC_USDT') === 'BTC_USDT' ? '#f7931a20' : '#627eea20',
                        }}>
                          {(s.symbol || 'BTC_USDT') === 'BTC_USDT' ? 'BTC' : 'ETH'}
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={styles.lockedItemName}>{s.name}</div>
                          {total > 0 && (
                            <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: wins >= losses ? 'var(--text)' : 'var(--down)' }}>
                              {wins}W / {losses}L
                            </span>
                          )}
                        </div>
                        <button
                          onClick={async () => {
                            try {
                              await unlockStrategy(parseInt(dur), s.id, s.symbol || 'BTC_USDT');
                              refresh();
                            } catch (e) {
                              setMessage('解锁失败: ' + (e.response?.data?.detail || e.message));
                            }
                          }}
                          title="取消"
                          style={styles.unlockItemBtn}
                        >✕</button>
                      </div>
                    )})}
                  </div>
                )}
              </div>
            )})}
          </div>
        </div>

        {/* 系统控制 */}
        <div style={styles.controlBlock}>
          <h3 style={styles.sectionTitle}>🎛 系统控制</h3>
          <div style={styles.controlRow}>
            <button
              onClick={() => handleControl(acc.status === 'RUNNING' ? 'pause' : 'resume')}
              style={acc.status === 'RUNNING' ? styles.pauseBtn : styles.resumeBtn}
            >
              {acc.status === 'RUNNING' ? '⏸ 暂停' : '▶ 启动'}
            </button>
          </div>
          {message && (
            <div style={{ ...styles.message, color: message.includes('失败') ? 'var(--down)' : 'var(--text)' }}>
              {message}
            </div>
          )}
        </div>

        {/* 仓位金额设置 */}
        <div style={styles.controlBlock}>
          <h3 style={styles.sectionTitle}>💰 每笔金额</h3>
          <PositionSizeInput
            value={acc.position_size || 100}
            onChange={async (val) => {
              try {
                await updateSettings({ position_size: val });
                setMessage('仓位金额已更新');
                refresh();
              } catch (e) {
                setMessage('更新失败: ' + (e.response?.data?.detail || e.message));
              }
            }}
          />
        </div>

        {/* 提示音开关 */}
        <div style={styles.controlBlock}>
          <h3 style={styles.sectionTitle}>🔔 提示音</h3>
          <button
            onClick={() => {
              const next = !soundOn;
              setSoundOn(next);
              localStorage.setItem('sim_sound', next ? 'on' : 'off');
              if (next) playBeep('win'); // 测试音
            }}
            style={{
              ...styles.soundToggle,
              background: soundOn ? 'var(--accent-dim)' : 'var(--surface-hover)',
              borderColor: soundOn ? 'var(--text)' : 'var(--border-light)',
              color: soundOn ? 'var(--text)' : 'var(--text-secondary)',
            }}
          >
            <span style={{ fontSize: 20 }}>{soundOn ? '🔔' : '🔕'}</span>
            <span style={{ fontSize: 13, fontWeight: 600 }}>
              {soundOn ? '已开启' : '已关闭'}
            </span>
          </button>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            开仓/平仓时播放提示音
          </div>
        </div>
      </div>

      {/* ═══════ 自动锁定策略 ═══════ */}
      <div style={{ ...styles.section, background: autoLock.enabled ? 'var(--accent-dim)' : 'var(--surface)', border: autoLock.enabled ? '1px solid var(--accent-dim)' : '1px solid var(--surface-hover)', borderRadius: 'var(--radius-lg)', padding: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h3 style={{ ...styles.sectionTitle, margin: 0 }}>🤖 自动锁定策略</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {!autoLock.enabled && [3, 5, 10].map(d => (
                <label key={d} style={{ fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3 }}>
                  <input type="checkbox" checked={autoLockSelected.includes(d)}
                    onChange={e => {
                      if (e.target.checked) setAutoLockSelected(prev => [...prev, d].sort());
                      else setAutoLockSelected(prev => prev.filter(x => x !== d));
                    }}
                  />
                  {d}m
                </label>
              ))}
            </div>
            <button
              onClick={async () => {
                if (autoLock.enabled) {
                  await autoLockStop();
                  setAutoLock(prev => ({ ...prev, enabled: false }));
                } else {
                  if (autoLockSelected.length === 0) return;
                  // 一次性提交所有本地设置
                  const s = localSettings;
                  await autoLockSettings({
                    backtest_hours: s.backtest_hours,
                    win_rate_threshold: s.win_rate_threshold,
                    min_trades: s.min_trades,
                    loss_streak_enabled: s.loss_streak_enabled,
                    loss_streak_max: s.loss_streak_max,
                    reverse_mode: s.reverse_mode,
                  });
                  await autoLockStart(autoLockSelected);
                  setAutoLock(prev => ({ ...prev, enabled: true }));
                }
              }}
              style={{
                padding: '6px 16px', borderRadius: 'var(--radius)', fontWeight: 700, fontSize: 13, cursor: 'pointer',
                background: autoLock.enabled ? 'var(--text-muted)' : 'var(--surface-hover)',
                color: 'var(--text)', border: 'none',
                opacity: !autoLock.enabled && autoLockSelected.length === 0 ? 0.5 : 1,
              }}
            >
              {autoLock.enabled ? '⏹ 关闭' : '▶ 开启'}
            </button>
          </div>
          {autoLock.enabled && (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {[3, 5, 10].map(d => {
                const ds = (autoLock.durations || {})[String(d)] || {};
                const st = ds.status || 'idle';
                const color = st === 'trading' ? 'var(--text)' : st === 'waiting' ? 'var(--text-secondary)' : 'var(--text)';
                const label = st === 'trading' ? '交易' : st === 'waiting' ? '等待' : st === 'searching' ? '搜索' : '关闭';
                const strat = ds.active_strategy;
                return (
                  <div key={d} style={{
                    background: 'var(--bg)', borderRadius: 'var(--radius)', padding: '6px 12px',
                    border: `1px solid ${color}44`, minWidth: 150,
                  }}>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{d}分钟 · {label}</div>
                    {strat && (
                      <>
                        <div style={{ fontSize: 12, fontWeight: 600, color }}>
                          {strat.name?.slice(0, 15)}
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                          回测胜率 {(strat.win_rate * 100).toFixed(0)}% · {strat.total_trades}笔
                          {ds.trade_count > 0 && <> · 实盘{ds.trade_count}笔</>}
                        </div>
                      </>
                    )}
                    {!strat && (
                      <div style={{ fontSize: 12, fontWeight: 600, color }}>{label}中...</div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
          {autoLock.enabled ? '运行中' : '开启后自动筛选策略并执行'}
        </div>

        {/* 参数设置 */}
        {!autoLock.enabled && (
          <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              回测:
              <select value={localSettings.backtest_hours}
                onChange={e => setLocalSettings(p => ({...p, backtest_hours: e.target.value}))}
                style={styles.setSelect}
              >
                <option value="1,2">1h→2h</option>
                <option value="2,4">2h→4h</option>
                <option value="1">仅1h</option>
                <option value="2">仅2h</option>
                <option value="4">仅4h</option>
              </select>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 3 }}>
              <input type="checkbox" checked={localSettings.reverse_mode}
                onChange={e => setLocalSettings(p => ({...p, reverse_mode: e.target.checked}))}
              />反向
              <span style={{ color: localSettings.reverse_mode ? 'var(--down)' : 'var(--text)' }}>{localSettings.reverse_mode ? '≤' : '≥'}</span>
              <input type="number" value={(localSettings.win_rate_threshold) * 100}
                onChange={e => setLocalSettings(p => ({...p, win_rate_threshold: parseFloat(e.target.value) / 100 || 0.01}))}
                style={styles.setInput} min={1} max={100} step={5}
              />%
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              交易≥
              <input type="number" value={localSettings.min_trades}
                onChange={e => setLocalSettings(p => ({...p, min_trades: parseInt(e.target.value) || 1}))}
                style={{ ...styles.setInput, width: 42 }} min={1} max={50}
              />笔
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 3 }}>
              <input type="checkbox" checked={localSettings.loss_streak_enabled}
                onChange={e => setLocalSettings(p => ({...p, loss_streak_enabled: e.target.checked}))}
              />
              连亏
              <input type="number" value={localSettings.loss_streak_max}
                onChange={e => setLocalSettings(p => ({...p, loss_streak_max: parseInt(e.target.value) || 1}))}
                style={{ ...styles.setInput, width: 35 }} min={1} max={10}
                disabled={!localSettings.loss_streak_enabled}
              />把换
            </div>
          </div>
        )}
      </div>

      {/* 市场方向 */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        {(() => {
          const btcPrices = priceData.map(d => d.BTC_USDT).filter(v => v != null);
          const trend = btcPrices.length > 20
            ? (btcPrices[btcPrices.length-1] > btcPrices[btcPrices.length-20] * 1.002 ? 'bull'
            : btcPrices[btcPrices.length-1] < btcPrices[btcPrices.length-20] * 0.998 ? 'bear'
            : 'range')
            : 'range';
          const trendLabel = trend === 'bull' ? '📈 看涨趋势' : trend === 'bear' ? '📉 看跌趋势' : '📊 震荡盘整';
          const trendColor = trend === 'bull' ? 'var(--text)' : trend === 'bear' ? 'var(--down)' : 'var(--text-secondary)';
          return (
            <div style={{
              background: 'var(--surface)', border: `1px solid ${trendColor}44`, borderRadius: 'var(--radius-lg)', padding: '10px 16px',
              flex: 1, minWidth: 200,
            }}>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>市场方向 (10分钟)</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: trendColor }}>{trendLabel}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                BTC: ${btcPrices[btcPrices.length-1]?.toFixed(0) || '—'}
                {btcPrices.length > 20 && ` · 变动 ${((btcPrices[btcPrices.length-1] / btcPrices[btcPrices.length-20] - 1) * 100).toFixed(2)}%`}
              </div>
            </div>
          );
        })()}
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '10px 16px',
          flex: 1, minWidth: 200,
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>系统状态</div>
          <div style={{ fontSize: 15, fontWeight: 700, color: acc.status === 'RUNNING' ? 'var(--text)' : 'var(--text-secondary)' }}>
            {acc.status === 'RUNNING' ? '▶ 运行中' : '⏸ 已暂停'}
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
            余额: ${acc.balance?.toFixed(2) || '0'} · 持仓: {acc.open_count || 0} · 已平: {acc.closed_count || 0}
          </div>
        </div>
      </div>

      {/* 胜率统计 */}
      {autoLock.stats && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
          {[3, 5, 10].map(d => {
            const st = autoLock.stats[String(d)] || {};
            const wr = (st.win_rate || 0) * 100;
            return (
              <div key={d} style={{
                background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '10px 16px',
                flex: 1, minWidth: 140,
              }}>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>{d}分钟合约</div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  <span style={{ color: wr >= 50 ? 'var(--text)' : 'var(--down)' }}>
                    胜率 {wr.toFixed(1)}%
                  </span>
                  <span style={{ color: 'var(--text-secondary)', marginLeft: 8, fontSize: 11 }}>
                    {st.wins || 0}W / {st.losses || 0}L
                  </span>
                </div>
                <div style={{ fontSize: 11, color: (st.total_pnl || 0) >= 0 ? 'var(--text)' : 'var(--down)', fontFamily: 'var(--font-mono)' }}>
                  PnL: {(st.total_pnl || 0) >= 0 ? '+' : ''}{(st.total_pnl || 0).toFixed(2)} USDT
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ═══════ 当前持仓 ═══════ */}
      <div style={styles.section}>
        <h3 style={styles.sectionTitle}>📌 当前持仓 ({acc.open_count || 0})</h3>
        {(!acc.open_positions || acc.open_positions.length === 0) ? (
          <div style={styles.noData}>暂无持仓</div>
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr style={styles.tableHeaderRow}>
                  <th style={styles.th}>品种</th>
                  <th style={styles.th}>时长</th>
                  <th style={styles.th}>方向</th>
                  <th style={styles.th}>入场价</th>
                  <th style={styles.th}>入场时间</th>
                  <th style={styles.th}>策略</th>
                </tr>
              </thead>
              <tbody>
                {acc.open_positions.map(p => (
                  <tr key={p.id}>
                    <td style={{ ...styles.td, fontWeight: 600 }}>{p.symbol}</td>
                    <td style={styles.td}>{p.duration}m</td>
                    <td style={{ ...styles.td, color: p.direction === 'UP' ? 'var(--text)' : 'var(--down)', fontWeight: 600 }}>
                      {p.direction}
                    </td>
                    <td style={{ ...styles.td, fontFamily: 'var(--font-mono)' }}>${p.entry_price?.toFixed(4)}</td>
                    <td style={{ ...styles.td, fontSize: 12 }}>{toLocalShort(p.entry_ts)}</td>
                    <td style={{ ...styles.td, fontSize: 12, color: 'var(--text-secondary)' }}>{p.strategy_name || p.strategy_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ═══════ 历史交易记录 ═══════ */}
      <div style={styles.section}>
        <h3 style={styles.sectionTitle}>
          📋 历史交易记录 ({history.length})
          <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>
            开仓点位 · 时间 · 输赢
          </span>
        </h3>
        {history.length === 0 ? (
          <div style={styles.noData}>暂无历史记录</div>
        ) : (
          <div style={{ ...styles.tableWrap, maxHeight: 360, overflowY: 'auto' }}>
            <table style={styles.table}>
              <thead>
                <tr style={{ ...styles.tableHeaderRow, position: 'sticky', top: 0, zIndex: 2 }}>
                  <th style={styles.th}>品种</th>
                  <th style={styles.th}>时长</th>
                  <th style={styles.th}>方向</th>
                  <th style={styles.th}>策略</th>
                  <th style={styles.th}>入场价</th>
                  <th style={styles.th}>入场时间</th>
                  <th style={styles.th}>出场价</th>
                  <th style={styles.th}>出场时间</th>
                  <th style={styles.th}>盈亏</th>
                  <th style={styles.th}>结果</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t, i) => (
                  <tr key={t.id || i} style={{
                    background: (t.pnl || 0) > 0 ? '#1a3a2a22' : '#3a1a1a22',
                  }}>
                    <td style={{ ...styles.td, fontWeight: 600 }}>{t.symbol}</td>
                    <td style={styles.td}>{t.duration}m</td>
                    <td style={{
                      ...styles.td,
                      color: t.direction === 'UP' ? 'var(--text)' : 'var(--down)',
                      fontWeight: 600,
                    }}>
                      {t.direction}
                    </td>
                    <td style={{ ...styles.td, fontSize: 11, color: 'var(--text-secondary)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={t.strategy_name || t.strategy_id || '—'}>
                      {t.strategy_name || t.strategy_id || '—'}
                    </td>
                    <td style={{ ...styles.td, fontFamily: 'var(--font-mono)' }}>
                      ${t.entry_price?.toFixed?.(4) || '—'}
                    </td>
                    <td style={{ ...styles.td, fontSize: 11 }}>
                      {toLocalShort(t.entry_ts)}
                    </td>
                    <td style={{ ...styles.td, fontFamily: 'var(--font-mono)' }}>
                      ${t.exit_price?.toFixed?.(4) || '—'}
                    </td>
                    <td style={{ ...styles.td, fontSize: 11 }}>
                      {toLocalShort(t.exit_ts)}
                    </td>
                    <td style={{
                      ...styles.td,
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 700,
                      color: (t.pnl || 0) >= 0 ? 'var(--text)' : 'var(--down)',
                    }}>
                      {(t.pnl || 0) >= 0 ? '+' : ''}{t.pnl?.toFixed?.(2) || '0'} USDT
                    </td>
                    <td style={styles.td}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: 10,
                        fontSize: 11,
                        fontWeight: 700,
                        background: (t.pnl || 0) > 0 ? 'var(--accent-dim)' : 'rgba(255,255,255,.03)',
                        color: (t.pnl || 0) > 0 ? 'var(--text)' : 'var(--down)',
                      }}>
                        {(t.pnl || 0) > 0 ? '✅ WIN' : '❌ LOSE'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ═══════ 观测池（扩展）═══════ */}
      <ObservationPool onLockChange={refresh} />

      {/* ═══════ 事件日志 ═══════ */}
      <div style={styles.section}>
        <h3 style={styles.sectionTitle}>📜 事件日志</h3>
        <div style={styles.logBox}>
          {(!acc.events || acc.events.length === 0) ? (
            <div style={styles.noData}>暂无事件</div>
          ) : (
            acc.events.slice().reverse().slice(0, 30).map((e, i) => (
              <div key={i} style={{
                ...styles.logLine,
                color: e.level === 'ERROR' ? 'var(--down)' : e.level === 'WARN' ? 'var(--text-secondary)' : 'var(--text-secondary)',
              }}>
                <span style={styles.logTs}>{e.ts?.slice(11, 19) || ''}</span>
                <span>[{e.level}]</span>
                <span>{e.msg}</span>
              </div>
            ))
          )}
        </div>
      </div>

    </div>
  );
}

// ═══ Memo 子组件（非价格数据不随 2s 刷新重渲染）═══

const PriceChartSection = memo(function PriceChartSection({ priceData, allPositions, sym }) {
  const markers = useMemo(() => allPositions.filter(p => p.symbol === sym).map(p => ({
    time: new Date(p.entry_ts).getTime(), price: p.entry_price, direction: p.direction, duration: p.duration, status: p.status, id: p.id,
  })), [allPositions, sym]);
  const opens = useMemo(() => allPositions.filter(p => p.symbol === sym && p.status === 'OPEN'), [allPositions, sym]);
  const formatTime = useCallback((ts) => new Date(ts).toLocaleTimeString(), []);
  const formatPrice = useCallback((v) => v?.toFixed?.(2) || '—', []);

  const yDomain = useMemo(() => {
    const vals = priceData.map(d => d[sym]).filter(v => v != null);
    if (vals.length < 2) return ['auto', 'auto'];
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const pad = (max - min) * 0.15 || max * 0.002;
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }, [priceData, sym]);

  const COLORS = { BTC_USDT: 'var(--text)', ETH_USDT: 'var(--text-secondary)' };
  const LABELS = { BTC_USDT: 'BTC/USDT', ETH_USDT: 'ETH/USDT' };
  const tooltipStyle = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text)' };

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0, color: COLORS[sym] }}>{LABELS[sym]}</h3>
        <span style={{ fontSize: 11, color: 'var(--text-secondary)', background: 'var(--surface-hover)', padding: '2px 8px', borderRadius: 10 }}>{markers.length} 笔标记</span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={priceData} margin={{ top: 10, right: 10, bottom: 5, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
          <XAxis dataKey="time" tickFormatter={formatTime} stroke="#484f58" fontSize={10} />
          <YAxis domain={yDomain} stroke="#484f58" fontSize={10} tickFormatter={v => v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v.toFixed(0)} width={55} allowDataOverflow />
          <Tooltip contentStyle={tooltipStyle} labelFormatter={formatTime} formatter={(val, name) => ['$' + formatPrice(val), LABELS[sym]]} />
          <Line type="monotone" dataKey={sym} name={LABELS[sym]} stroke={COLORS[sym]} strokeWidth={2} dot={false} isAnimationActive={false} />
          {markers.slice(-10).map(m => (
            <ReferenceLine key={m.id} y={m.price} stroke={m.direction === 'UP' ? 'var(--text)' : 'var(--down)'} strokeDasharray={m.status === 'OPEN' ? '2 2' : '6 3'} strokeWidth={m.status === 'OPEN' ? 1.5 : 0.8} opacity={m.status === 'OPEN' ? 1 : 0.5}
              label={{ value: `${m.direction === 'UP' ? '▲' : '▼'} ${m.duration}m`, fill: m.direction === 'UP' ? 'var(--text)' : 'var(--down)', fontSize: 9, position: 'right' }} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      {markers.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          {markers.slice(-5).reverse().map(m => (
            <span key={m.id} style={{ padding: '2px 8px', borderRadius: 4, fontSize: 10, fontFamily: 'var(--font-mono)', border: '1px solid', whiteSpace: 'nowrap', color: m.direction === 'UP' ? 'var(--text)' : 'var(--down)', borderColor: m.status === 'OPEN' ? (m.direction === 'UP' ? 'var(--text)' : 'var(--down)') : 'var(--border-light)', background: m.status === 'OPEN' ? (m.direction === 'UP' ? 'var(--accent-dim)' : 'rgba(255,255,255,.02)') : 'transparent' }}>
              {m.direction === 'UP' ? '▲' : '▼'} {m.duration}m @{m.price?.toFixed(1)}{m.status === 'OPEN' && ' ●'}
            </span>
          ))}
        </div>
      )}
    </div>
  );
});

const HistoryTable = memo(function HistoryTable({ history }) {
  if (history.length === 0) return <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)', fontSize: 13 }}>暂无历史记录</div>;
  const toLocalShort = (isoStr) => { if (!isoStr) return '—'; const d = new Date(isoStr); if (isNaN(d.getTime())) return isoStr; const pad = (n) => String(n).padStart(2, '0'); return `${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
  return (
    <div style={{ maxHeight: 360, overflowY: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, color: 'var(--text)' }}>
        <thead>
          <tr style={{ position: 'sticky', top: 0, zIndex: 2, background: 'var(--bg)' }}>
            <th style={tStyle}>品种</th><th style={tStyle}>时长</th><th style={tStyle}>方向</th><th style={tStyle}>入场价</th><th style={tStyle}>入场时间</th><th style={tStyle}>出场价</th><th style={tStyle}>出场时间</th><th style={tStyle}>盈亏</th><th style={tStyle}>结果</th>
          </tr>
        </thead>
        <tbody>
          {history.map((t, i) => (
            <tr key={t.id || i} style={{ background: (t.pnl || 0) > 0 ? '#1a3a2a22' : '#3a1a1a22' }}>
              <td style={{ ...tStyle, fontWeight: 600 }}>{t.symbol}</td>
              <td style={tStyle}>{t.duration}m</td>
              <td style={{ ...tStyle, color: t.direction === 'UP' ? 'var(--text)' : 'var(--down)', fontWeight: 600 }}>{t.direction}</td>
              <td style={{ ...tStyle, fontFamily: 'var(--font-mono)' }}>${t.entry_price?.toFixed?.(4) || '—'}</td>
              <td style={{ ...tStyle, fontSize: 11 }}>{toLocalShort(t.entry_ts)}</td>
              <td style={{ ...tStyle, fontFamily: 'var(--font-mono)' }}>${t.exit_price?.toFixed?.(4) || '—'}</td>
              <td style={{ ...tStyle, fontSize: 11 }}>{toLocalShort(t.exit_ts)}</td>
              <td style={{ ...tStyle, fontFamily: 'var(--font-mono)', fontWeight: 700, color: (t.pnl || 0) >= 0 ? 'var(--text)' : 'var(--down)' }}>{(t.pnl || 0) >= 0 ? '+' : ''}{t.pnl?.toFixed?.(2) || '0'} USDT</td>
              <td style={tStyle}><span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 700, background: (t.pnl || 0) > 0 ? 'var(--accent-dim)' : 'rgba(255,255,255,.03)', color: (t.pnl || 0) > 0 ? 'var(--text)' : 'var(--down)' }}>{(t.pnl || 0) > 0 ? '✅ WIN' : '❌ LOSE'}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
});

const tStyle = { padding: '6px 12px', borderBottom: '1px solid #21262d', whiteSpace: 'nowrap' };

const EventLog = memo(function EventLog({ events }) {
  if (!events || events.length === 0) return <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)', fontSize: 13 }}>暂无事件</div>;
  return (
    <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '10px 14px', maxHeight: 260, overflowY: 'auto', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
      {events.slice().reverse().slice(0, 30).map((e, i) => (
        <div key={i} style={{ padding: '2px 0', display: 'flex', gap: 8, color: e.level === 'ERROR' ? 'var(--down)' : e.level === 'WARN' ? 'var(--text-secondary)' : 'var(--text-secondary)' }}>
          <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{e.ts?.slice(11, 19) || ''}</span>
          <span>[{e.level}]</span>
          <span>{e.msg}</span>
        </div>
      ))}
    </div>
  );
});

// ── 仓位金额输入子组件 ──
function PositionSizeInput({ value, onChange }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(value));

  const presets = [50, 100, 200, 500, 1000];

  const apply = (val) => {
    const n = parseFloat(val);
    if (n >= 1 && n <= 100000) {
      onChange(n);
      setDraft(String(n));
    }
    setEditing(false);
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {editing ? (
          <>
            <input
              type="number"
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') apply(draft); if (e.key === 'Escape') setEditing(false); }}
              style={styles.sizeInput}
              min={1}
              max={100000}
              autoFocus
            />
            <button onClick={() => apply(draft)} style={styles.applyBtn}>✓</button>
            <button onClick={() => { setDraft(String(value)); setEditing(false); }} style={styles.cancelBtn}>✕</button>
          </>
        ) : (
          <>
            <span style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
              ${value}
            </span>
            <button onClick={() => { setDraft(String(value)); setEditing(true); }} style={styles.editBtn}>
              ✎ 修改
            </button>
          </>
        )}
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {presets.map(p => (
          <button
            key={p}
            onClick={() => onChange(p)}
            style={{
              ...styles.presetBtn,
              background: value === p ? 'rgba(255,255,255,.08)' : 'var(--surface-hover)',
              color: value === p ? 'var(--text)' : 'var(--text-secondary)',
              borderColor: value === p ? 'var(--text)' : 'var(--border-light)',
            }}
          >
            ${p}
          </button>
        ))}
      </div>
    </div>
  );
}

const styles = {
  empty: { textAlign: 'center', padding: 80, color: 'var(--text-muted)', fontSize: 16 },

  // Toast
  toastLayer: { position: 'fixed', top: 16, right: 16, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 380 },
  toast: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '14px 18px', borderRadius: 10,
    background: 'var(--surface)', border: '1px solid var(--border)',
    fontSize: 13, color: 'var(--text)',
    boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
    animation: 'slideIn 0.3s ease',
  },
  toastOpen: { borderColor: 'var(--text)', borderLeft: '3px solid #58a6ff' },
  toastWin: { borderColor: 'var(--text)', borderLeft: '3px solid #3fb950' },
  toastLose: { borderColor: 'var(--down)', borderLeft: '3px solid #f85149' },
  toastClose: { marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 14, cursor: 'pointer', padding: '2px 6px' },

  // 异常弹窗
  alert: { display: 'flex', gap: 16, padding: '20px 24px', background: 'var(--accent-dim)', border: '1px solid #d29922', borderRadius: 'var(--radius-lg)', marginBottom: 20 },
  alertIcon: { fontSize: 32 },
  alertBody: { flex: 1 },
  alertTitle: { fontSize: 16, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 8 },
  alertMsg: { fontSize: 13, color: 'var(--text)', marginBottom: 12, fontFamily: 'var(--font-mono)' },
  alertActions: { display: 'flex', gap: 10 },
  confirmBtn: { padding: '8px 20px', background: 'var(--surface-hover)', color: 'var(--text)', border: 'none', borderRadius: 'var(--radius)', fontSize: 13, fontWeight: 600 },
  abortBtn: { padding: '8px 20px', background: 'var(--surface-hover)', color: 'var(--down)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', fontSize: 13 },

  // 指标
  overviewGrid: { display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 12, marginBottom: 20 },
  card: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' },
  cardLabel: { fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 },
  cardValue: { fontSize: 18, fontWeight: 700, fontFamily: 'var(--font-mono)' },

  // 行情图
  chartsGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 },
  chartBox: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 16 },
  chartHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  chartTitle: { fontSize: 14, fontWeight: 600, margin: 0 },
  chartBadge: { fontSize: 11, color: 'var(--text-secondary)', background: 'var(--surface-hover)', padding: '2px 8px', borderRadius: 10 },
  markerList: { display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 },
  markerTag: {
    padding: '2px 8px', borderRadius: 4, fontSize: 10, fontFamily: 'var(--font-mono)',
    border: '1px solid', whiteSpace: 'nowrap',
  },

  // 控制面板（4 列）
  controlPanel: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 20 },
  controlBlock: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '14px 18px' },
  sectionTitle: { fontSize: 13, fontWeight: 600, marginBottom: 10, color: 'var(--text)' },
  lockedGrid: { display: 'flex', gap: 8 },
  lockedCard: { flex: 1, background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '8px 12px', transition: 'border-color 0.2s' },
  lockedDur: { fontSize: 10, color: 'var(--text-secondary)', marginBottom: 4 },
  lockedName: { fontSize: 13, fontWeight: 600 },
  lockedItem: {
    display: 'flex', alignItems: 'center', gap: 4,
    padding: '2px 4px', borderRadius: 3,
    background: 'var(--bg)',
  },
  lockedItemName: { fontSize: 11, fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  symBadge: {
    fontSize: 9, fontWeight: 700, padding: '1px 4px', borderRadius: 2,
    fontFamily: 'var(--font-mono)', flexShrink: 0,
  },
  setSelect: { padding: '2px 4px', background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 3, fontSize: 11, marginLeft: 4 },
  setInput: { padding: '2px 4px', background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 3, fontSize: 11, width: 40, textAlign: 'center', marginLeft: 4 },
  unlockItemBtn: {
    background: 'none', border: 'none', color: 'var(--down)',
    fontSize: 12, cursor: 'pointer', padding: '0 4px',
    opacity: 0.5, flexShrink: 0,
  },
  unlockBtn: {
    position: 'absolute', top: 4, right: 6,
    background: 'none', border: 'none',
    color: 'var(--down)', fontSize: 14, fontWeight: 700,
    cursor: 'pointer', padding: '2px 6px', borderRadius: 3,
    opacity: 0.5,
  },
  controlRow: { display: 'flex', gap: 8 },
  pauseBtn: { padding: '8px 20px', background: 'var(--surface-hover)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', fontSize: 14, fontWeight: 600, cursor: 'pointer' },
  resumeBtn: { padding: '8px 20px', background: 'var(--surface-hover)', color: 'var(--text)', border: 'none', borderRadius: 'var(--radius)', fontSize: 14, fontWeight: 600, cursor: 'pointer' },
  message: { marginTop: 8, fontSize: 12, fontFamily: 'var(--font-mono)' },

  // 仓位金额
  sizeInput: { width: 80, padding: '4px 8px', background: 'var(--bg)', color: 'var(--text)', border: '1px solid #58a6ff', borderRadius: 4, fontSize: 14, fontFamily: 'var(--font-mono)', textAlign: 'center' },
  applyBtn: { padding: '4px 8px', background: 'var(--surface-hover)', color: 'var(--text)', border: 'none', borderRadius: 4, fontSize: 12, cursor: 'pointer' },
  cancelBtn: { padding: '4px 8px', background: 'var(--surface-hover)', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 4, fontSize: 12, cursor: 'pointer' },
  editBtn: { padding: '2px 8px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 4, fontSize: 11, cursor: 'pointer' },
  presetBtn: { padding: '3px 8px', border: '1px solid', borderRadius: 4, fontSize: 11, cursor: 'pointer', fontFamily: 'var(--font-mono)', transition: 'all 0.15s' },

  // 提示音
  soundToggle: { display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px', border: '1px solid', borderRadius: 'var(--radius-lg)', cursor: 'pointer', transition: 'all 0.2s', width: '100%' },

  // 持仓 + 日志
  rowGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 },

  // 表格
  noData: { textAlign: 'center', padding: 24, color: 'var(--text-muted)', fontSize: 13 },
  tableWrap: { overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13, color: 'var(--text)' },
  tableHeaderRow: { position: 'sticky', top: 0, background: 'var(--bg)' },
  th: { padding: '6px 10px', textAlign: 'left', borderBottom: '1px solid #30363d', color: 'var(--text-secondary)', fontWeight: 600, fontSize: 11, whiteSpace: 'nowrap' },
  td: { padding: '6px 10px', borderBottom: '1px solid #21262d', whiteSpace: 'nowrap' },

  // 日志
  logBox: { background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '10px 14px', maxHeight: 260, overflowY: 'auto', fontFamily: 'var(--font-mono)', fontSize: 12 },
  logLine: { padding: '2px 0', display: 'flex', gap: 8 },
  logTs: { color: 'var(--text-muted)', flexShrink: 0 },
};
