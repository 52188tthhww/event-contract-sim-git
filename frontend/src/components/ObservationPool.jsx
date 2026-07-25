/**
 * 观测池面板 — 独立组件，嵌入 SimAccount
 * 展示全部策略，每策略×时长独立锁定按钮
 */
import React, { useEffect, useState } from 'react';
import { getPoolStats, resetPool, lockStrategy, unlockStrategy } from '../ext_api';
import axios from 'axios';

const API = process.env.REACT_APP_API ?? '';

export default function ObservationPool({ onLockChange }) {
  const [pool, setPool] = useState({ stats: {}, open_count: 0, closed_count: 0 });
  const [allStrategies, setAllStrategies] = useState([]);
  const [message, setMessage] = useState('');

  // 全策略列表（只加载一次）
  useEffect(() => {
    axios.get(`${API}/strategies`).then(r => setAllStrategies(r.data.strategies || [])).catch(() => {});
  }, []);

  // 5 秒轮询观测池数据
  useEffect(() => {
    const fetch = () => getPoolStats().then(setPool).catch(() => {});
    fetch();
    const iv = setInterval(fetch, 5000);
    return () => clearInterval(iv);
  }, []);

  const handleReset = async () => {
    if (!window.confirm('确认清空观测池全部数据？')) return;
    try {
      await resetPool();
      setPool({ stats: {}, open_count: 0, closed_count: 0 });
      setMessage('观测池已重新初始化');
    } catch (e) {
      setMessage(`重置失败: ${e.response?.data?.detail || e.message}`);
    }
  };

  const handleLock = async (sid, name, dur, symbol) => {
    try {
      await lockStrategy({ strategy_id: sid, duration: dur, symbol });
      setMessage(`${name} ${dur}min 已锁定`);
      if (onLockChange) onLockChange();
    } catch (e) {
      setMessage(`操作失败: ${e.response?.data?.detail || e.message}`);
    }
  };

  const stats = pool.stats || {};

  // 合并全策略列表与观测池数据
  const merged = allStrategies.map(s => ({
    id: s.id,
    name: s.name,
    d3: (stats[s.id] && stats[s.id]['3']) || { wins: 0, losses: 0 },
    d5: (stats[s.id] && stats[s.id]['5']) || { wins: 0, losses: 0 },
    d10: (stats[s.id] && stats[s.id]['10']) || { wins: 0, losses: 0 },
    total: ((stats[s.id]?.['3']?.wins||0)+(stats[s.id]?.['3']?.losses||0)+
            (stats[s.id]?.['5']?.wins||0)+(stats[s.id]?.['5']?.losses||0)+
            (stats[s.id]?.['10']?.wins||0)+(stats[s.id]?.['10']?.losses||0)),
  }));

  // 有数据的排前面
  merged.sort((a, b) => b.total - a.total);

  const renderCell = (d, dur, sid, name) => {
    const total = d.wins + d.losses;
    if (total === 0) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
          <span style={{ color: '#484f58', fontSize: 11 }}>—</span>
          <button onClick={() => handleLock(sid, name, dur, 'BTC_USDT')}
            style={{ padding: '1px 6px', borderRadius: 4, fontSize: 11, cursor: 'pointer',
              background: '#21262d', color: '#484f58', border: '1px solid #30363d' }}>
            🔓
          </button>
        </div>
      );
    }
    const wr = (d.wins / total * 100).toFixed(0);
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
        <span style={{ fontFamily: 'monospace', fontSize: 11, color: +wr >= 50 ? '#3fb950' : '#f85149' }}>
          {d.wins}W/{d.losses}L ({wr}%)
        </span>
        <button onClick={() => handleLock(sid, name, dur, 'BTC_USDT')}
          style={{ padding: '1px 6px', borderRadius: 4, fontSize: 11, cursor: 'pointer',
            background: '#21262d', color: '#484f58', border: '1px solid #30363d' }}>
          🔓
        </button>
      </div>
    );
  };

  return (
    <div style={{ background: '#161b22', border: '1px solid #21262d', borderRadius: 8, padding: 16, marginTop: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0, color: '#e1e4e8' }}>
          🔍 观测池
          <span style={{ fontSize: 11, color: '#484f58', marginLeft: 8 }}>
            OPEN {pool.open_count} | CLOSED {pool.closed_count} 笔 | {allStrategies.length} 策略
          </span>
        </h3>
        <button onClick={handleReset}
          style={{ padding: '4px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
            background: '#21262d', color: '#f85149', border: '1px solid #30363d', cursor: 'pointer' }}>
          🔄 重新初始化
        </button>
      </div>
      {message && (
        <div style={{ fontSize: 12, color: '#d29922', marginBottom: 6 }}>{message}</div>
      )}
      <div style={{ maxHeight: 400, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, color: '#e1e4e8' }}>
          <thead>
            <tr style={{ position: 'sticky', top: 0, zIndex: 2, background: '#0d1117' }}>
              <th style={th}>策略</th>
              <th style={{ ...th, textAlign: 'center' }}>3min</th>
              <th style={{ ...th, textAlign: 'center' }}>5min</th>
              <th style={{ ...th, textAlign: 'center' }}>10min</th>
            </tr>
          </thead>
          <tbody>
            {merged.map(s => (
              <tr key={s.id}>
                <td style={{ ...td, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    title={s.name}>{s.name}</td>
                <td style={{ ...td, textAlign: 'center' }}>{renderCell(s.d3, 3, s.id, s.name)}</td>
                <td style={{ ...td, textAlign: 'center' }}>{renderCell(s.d5, 5, s.id, s.name)}</td>
                <td style={{ ...td, textAlign: 'center' }}>{renderCell(s.d10, 10, s.id, s.name)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th = { padding: '8px 8px', fontSize: 12, fontWeight: 600, color: '#8b949e', borderBottom: '1px solid #21262d', textAlign: 'left' };
const td = { padding: '6px 8px', fontSize: 12, borderBottom: '1px solid #0d1117' };
