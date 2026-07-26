import React, { useState, useEffect, useCallback } from 'react';
import { runBacktest, lockStrategy, unlockStrategy, getStrategies, getReports, getAccount } from '../api';

const DURATIONS = [3, 5, 10];
const COLORS = { BTC_USDT: '#fff', ETH_USDT: '#aaa' };

export default function BacktestPanel({ onTrace }) {
  const [symbol, setSymbol] = useState('BTC_USDT');
  const [hours, setHours] = useState(4);
  const [reports, setReports] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  // 胜率筛选: 显示 >=minWin 或 <=maxWin
  const [minWin, setMinWin] = useState(55);
  const [maxWin, setMaxWin] = useState(30);
  // 追踪已锁定的策略 {duration: [{id, name, symbol}]}
  const [lockedMap, setLockedMap] = useState({});
  const [lockMsg, setLockMsg] = useState('');
  // 每行独立的品种选择 {`${duration}_${strategy_id}`: 'BTC_USDT' | 'ETH_USDT'}
  const [rowSymbols, setRowSymbols] = useState({});

  // 加载策略列表
  useEffect(() => {
    getStrategies().then(res => {
      setStrategies(res.strategies || []);
    }).catch(() => {});
  }, []);

  // 定期同步锁定状态（多策略数组）
  useEffect(() => {
    const iv = setInterval(() => {
      getAccount().then(acc => {
        if (acc.locked) {
          const map = {};
          for (const [dur, list] of Object.entries(acc.locked)) {
            map[parseInt(dur)] = Array.isArray(list) ? list : [];
          }
          setLockedMap(map);
        }
      }).catch(() => {});
    }, 3000);
    return () => clearInterval(iv);
  }, []);

  // 自动刷新
  useEffect(() => {
    if (!autoRefresh) return;
    const iv = setInterval(() => {
      getReports().then(res => {
        const all = (res.reports || []).flatMap(r => r.reports || []);
        if (all.length) setReports(all);
      }).catch(() => {});
    }, 5000);
    return () => clearInterval(iv);
  }, [autoRefresh]);

  const handleRun = useCallback(async () => {
    setLoading(true);
    try {
      const res = await runBacktest({
        symbol, duration_hours: hours,
        min_win_rate: minWin / 100,
        max_win_rate: maxWin / 100,
      });
      const all = (res[0]?.reports || []).map(r => ({ ...r, _symbol: symbol }));
      setReports(all);
    } catch (e) {
      setReports([]);
      setLockMsg('回测失败: ' + (e.response?.data?.detail || e.message));
      setTimeout(() => setLockMsg(''), 5000);
    }
    setLoading(false);
  }, [symbol, hours, minWin, maxWin]);

  const handleLock = useCallback(async (duration, strategyId, strategyName, symbol) => {
    setLockMsg('');
    try {
      // 检查是否已锁定这个具体策略
      const currentList = lockedMap[duration] || [];
      const alreadyLocked = currentList.find(s => s.id === strategyId && s.symbol === symbol);
      if (alreadyLocked) {
        // 解锁
        await unlockStrategy(duration, strategyId);
        setLockedMap(prev => ({
          ...prev,
          [duration]: (prev[duration] || []).filter(s => s.id !== strategyId),
        }));
        setLockMsg(`${symbol} ${duration}m ${strategyName} 已解锁`);
      } else {
        // 新锁定
        await lockStrategy({ duration, strategy_id: strategyId, symbol });
        setLockedMap(prev => ({
          ...prev,
          [duration]: [...(prev[duration] || []), { id: strategyId, name: strategyName, symbol }],
        }));
        setLockMsg(`${symbol} ${duration}m ${strategyName} 锁定成功`);
      }
      setTimeout(() => setLockMsg(''), 3000);
    } catch (e) {
      setLockMsg('操作失败: ' + (e.response?.data?.detail || e.message));
    }
  }, [lockedMap]);

  // 分组展示：按 duration 分组，每组内按 qualified > win_rate 排序
  const grouped = {};
  for (const r of reports) {
    const d = r.duration;
    if (!grouped[d]) grouped[d] = [];
    grouped[d].push(r);
  }

  return (
    <div>
      {/* 配置栏 */}
      <div style={styles.controlBar}>
        <div style={styles.field}>
          <label style={styles.label}>品种</label>
          <select
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            style={styles.select}
          >
            <option value="BTC_USDT">BTC/USDT</option>
            <option value="ETH_USDT">ETH/USDT</option>
          </select>
        </div>
        <div style={styles.field}>
          <label style={styles.label}>回溯时长</label>
          <input
            type="number"
            value={hours}
            onChange={e => setHours(Math.max(1, Math.min(72, +e.target.value)))}
            style={styles.input}
            min={1}
            max={72}
          />
          <span style={styles.unit}>小时</span>
        </div>
        <div style={styles.field}>
          <label style={styles.label}>胜率</label>
          <span style={{ fontSize: 11, color: '#fff' }}>≥</span>
          <input type="number" value={minWin} onChange={e => setMinWin(Math.max(0, Math.min(100, +e.target.value)))}
            style={{ ...styles.input, width: 42 }} min={0} max={100} />
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>%</span>
          <span style={{ fontSize: 11, color: '#555', marginLeft: 4 }}>≤</span>
          <input type="number" value={maxWin} onChange={e => setMaxWin(Math.max(0, Math.min(100, +e.target.value)))}
            style={{ ...styles.input, width: 42 }} min={0} max={100} />
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>%</span>
        </div>
        <button onClick={handleRun} disabled={loading} style={styles.runBtn}>
          {loading ? '⏳ 回测中...' : '▶ 运行回测'}
        </button>
        <label style={styles.autoLabel}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={e => setAutoRefresh(e.target.checked)}
          />
          {' '}每 60s 自动刷新
        </label>
      </div>

      {/* 策略总数 + 锁定状态 */}
      <div style={styles.summary}>
        共 <b>{strategies.length}</b> 条策略 × <b>{DURATIONS.length}</b> 个合约时长
        = <b>{strategies.length * DURATIONS.length}</b> 个回测组合
        {reports.length > 0 && (
          <> | 筛选结果: <b style={{ color: '#fff' }}>{reports.length}</b> 条
            (≥{minWin}%: <b style={{ color: '#fff' }}>{reports.filter(r => r.win_rate >= minWin/100).length}</b>
            {' '}≤{maxWin}%: <b style={{ color: '#555' }}>{reports.filter(r => r.win_rate <= maxWin/100).length}</b>)
          </>)}
        {Object.values(lockedMap).some(arr => arr.length > 0) && (
          <> | 已锁定: <b style={{ color: '#fff' }}>
            {Object.entries(lockedMap).filter(([,arr]) => arr.length > 0).map(([k, arr]) => `${k}m×${arr.length}`).join(', ')}
          </b></>
        )}
      </div>
      {lockMsg && (
        <div style={{
          ...styles.lockMsg,
          color: lockMsg.includes('失败') ? '#555' : '#fff',
        }}>
          {lockMsg}
        </div>
      )}

      {/* 报表 */}
      {DURATIONS.map(dur => {
        const items = (grouped[dur] || []).slice(0, 20); // 每时长最多展示 20 条
        if (!items.length) return null;
        return (
          <div key={dur} style={styles.group}>
            <h3 style={styles.groupTitle}>⏱ {dur} 分钟事件合约</h3>
            <div style={styles.tableWrap}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th>策略</th>
                    <th>交易数</th>
                    <th>胜场</th>
                    <th>胜率</th>
                    <th>净盈亏</th>
                    <th>期望值</th>
                    <th>均盈</th>
                    <th>均亏</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r, i) => (
                    <tr
                      key={`${r.strategy_id}-${i}`}
                      style={r.qualified ? styles.rowQualified : {}}
                    >
                      <td style={styles.stratName}>
                        {r.qualified && <span style={styles.badge}>★</span>}
                        {r.strategy_name}
                      </td>
                      <td>{r.total_trades}</td>
                      <td style={{ color: '#fff' }}>{r.wins}</td>
                      <td>
                        <span style={{
                          color: r.win_rate >= 0.75 ? '#fff' : r.win_rate >= 0.5 ? '#888' : '#555',
                          fontWeight: 600,
                        }}>
                          {(r.win_rate * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td style={{ color: r.net_pnl >= 0 ? '#fff' : '#555', fontFamily: 'var(--font-mono)' }}>
                        {r.net_pnl >= 0 ? '+' : ''}{r.net_pnl}
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{r.expectancy}</td>
                      <td style={{ color: '#fff', fontFamily: 'var(--font-mono)' }}>{r.avg_win}</td>
                      <td style={{ color: '#555', fontFamily: 'var(--font-mono)' }}>{r.avg_loss}</td>
                      <td>
                        <div style={styles.actionRow}>
                          <button
                            onClick={() => onTrace(r)}
                            style={styles.traceBtn}
                          >
                            溯源
                          </button>
                          {(() => {
                            const currentList = lockedMap[r.duration] || [];
                            const lockedEntry = currentList.find(s => s.id === r.strategy_id);
                            const isThisLocked = !!lockedEntry;
                            const rowKey = `${r.duration}_${r.strategy_id}`;
                            const rowSym = rowSymbols[rowKey] || 'BTC_USDT';
                            const sym = lockedEntry?.symbol || rowSym;
                            return (
                              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                                {isThisLocked ? (
                                  <>
                                    <span style={{
                                      ...styles.lockedBadge,
                                      background: sym === 'BTC_USDT' ? '#f7931a25' : '#627eea25',
                                      color: sym === 'BTC_USDT' ? '#fff' : '#aaa',
                                      borderColor: sym === 'BTC_USDT' ? '#f7931a55' : '#627eea55',
                                    }}>
                                      {sym === 'BTC_USDT' ? 'BTC' : 'ETH'}
                                    </span>
                                    <span style={{ fontSize: 12, color: '#fff', fontWeight: 600 }}>已锁定</span>
                                    <button
                                      onClick={() => handleLock(r.duration, r.strategy_id, r.strategy_name, sym)}
                                      style={styles.unlockBtnSmall}
                                      title="点击取消锁定"
                                    >
                                      取消
                                    </button>
                                  </>
                                ) : (
                                  <>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); setRowSymbols(p => ({...p, [rowKey]: 'BTC_USDT'})); }}
                                      style={{
                                        ...styles.symBtnBig,
                                        background: rowSym === 'BTC_USDT' ? '#f7931a30' : '#0d1117',
                                        color: rowSym === 'BTC_USDT' ? '#fff' : '#8b949e',
                                        borderColor: rowSym === 'BTC_USDT' ? '#fff' : '#30363d',
                                      }}
                                    >BTC</button>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); setRowSymbols(p => ({...p, [rowKey]: 'ETH_USDT'})); }}
                                      style={{
                                        ...styles.symBtnBig,
                                        background: rowSym === 'ETH_USDT' ? '#627eea30' : '#0d1117',
                                        color: rowSym === 'ETH_USDT' ? '#aaa' : '#8b949e',
                                        borderColor: rowSym === 'ETH_USDT' ? '#aaa' : '#30363d',
                                      }}
                                    >ETH</button>
                                    <button
                                      onClick={() => handleLock(r.duration, r.strategy_id, r.strategy_name, rowSym)}
                                      style={{
                                        ...styles.lockBtn,
                                        ...(r.qualified ? styles.lockBtnQualified : {}),
                                      }}
                                    >
                                      {r.qualified ? '★ 锁定' : '锁定'}
                                    </button>
                                  </>
                                )}
                              </div>
                            );
                          })()}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}

      {reports.length === 0 && !loading && (
        <div style={styles.empty}>
          点击「运行回测」开始分析历史数据
        </div>
      )}
    </div>
  );
}

const styles = {
  controlBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    flexWrap: 'wrap',
    padding: '16px 20px',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    marginBottom: 16,
  },
  field: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  label: {
    fontSize: 13,
    color: 'var(--text-secondary)',
  },
  select: {
    padding: '6px 12px',
    background: 'var(--bg-deep)',
    color: '#e6edf3',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    fontSize: 13,
  },
  input: {
    width: 60,
    padding: '6px 8px',
    background: 'var(--bg-deep)',
    color: '#e6edf3',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    fontSize: 13,
    textAlign: 'center',
  },
  unit: {
    fontSize: 12,
    color: 'var(--text-secondary)',
  },
  runBtn: {
    padding: '8px 24px',
    background: '#333',
    color: '#fff',
    border: 'none',
    borderRadius: 'var(--radius-sm)',
    fontSize: 14,
    fontWeight: 600,
  },
  autoLabel: {
    fontSize: 12,
    color: 'var(--text-secondary)',
    marginLeft: 'auto',
  },
  summary: {
    fontSize: 12,
    color: 'var(--text-secondary)',
    marginBottom: 16,
  },
  group: {
    marginBottom: 24,
  },
  groupTitle: {
    fontSize: 15,
    fontWeight: 600,
    marginBottom: 8,
    color: '#e6edf3',
  },
  tableWrap: {
    overflowX: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 13,
  },
  rowQualified: {
    background: '#1a3a2a',
  },
  badge: {
    color: '#fff',
    marginRight: 4,
  },
  stratName: {
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  actionRow: {
    display: 'flex',
    gap: 6,
  },
  traceBtn: {
    padding: '4px 12px',
    background: '#21262d',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border)',
    borderRadius: 4,
    fontSize: 12,
  },
  lockBtn: {
    padding: '4px 12px',
    background: '#21262d',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border)',
    borderRadius: 4,
    fontSize: 12,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  lockBtnActive: {
    background: 'rgba(255,255,255,.08)',
    color: '#fff',
    borderColor: '#fff',
  },
  symBtn: {
    padding: '2px 6px',
    border: '1px solid',
    borderRadius: 3,
    fontSize: 10,
    fontWeight: 700,
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    transition: 'all 0.1s',
  },
  symBtnBig: {
    padding: '4px 10px',
    border: '1px solid',
    borderRadius: 4,
    fontSize: 12,
    fontWeight: 700,
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    transition: 'all 0.15s',
  },
  lockedBadge: {
    padding: '3px 8px',
    border: '1px solid',
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 700,
    fontFamily: 'var(--font-mono)',
  },
  unlockBtnSmall: {
    padding: '3px 8px',
    background: 'transparent',
    color: '#555',
    border: '1px solid #f8514955',
    borderRadius: 4,
    fontSize: 11,
    cursor: 'pointer',
  },
  lockBtnQualified: {
    background: '#333',
    color: '#fff',
    border: 'none',
    fontWeight: 600,
  },
  lockMsg: {
    padding: '8px 16px',
    borderRadius: 'var(--radius-sm)',
    marginBottom: 12,
    fontSize: 13,
    fontWeight: 500,
  },
  empty: {
    textAlign: 'center',
    padding: 60,
    color: 'var(--text-muted)',
    fontSize: 15,
  },
};
