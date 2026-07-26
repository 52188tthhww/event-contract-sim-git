import React, { useEffect, useState, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Area, ComposedChart
} from 'recharts';
import { getPrices } from '../api';
import axios from 'axios';

const API = process.env.REACT_APP_API ?? '';
const http = axios.create({ baseURL: API, timeout: 30000 });

const COLORS = { BTC_USDT: '#f7931a', ETH_USDT: '#627eea' };
const LABELS = { BTC_USDT: 'BTC/USDT', ETH_USDT: 'ETH/USDT' };

// Tooltip component with better formatting
const ChartTooltip = ({ active, payload, label, symbol }) => {
  if (!active || !payload?.length) return null;
  const d = new Date(label);
  const time = d.toLocaleTimeString();
  const price = payload[0]?.value;
  return (
    <div style={{ background: '#0d1117', border: '1px solid rgba(255,255,255,.12)', borderRadius: 8, padding: '10px 14px', fontSize: 13 }}>
      <div style={{ color: '#8896a4', fontSize: 11, marginBottom: 4 }}>{time}</div>
      <div style={{ color: COLORS[symbol], fontWeight: 600, fontFamily: 'var(--font-mono)', fontSize: 15 }}>
        ${price?.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 })}
      </div>
    </div>
  );
};

export default function PriceChart() {
  const [data, setData] = useState([]);
  const [metrics, setMetrics] = useState({});
  const timerRef = useRef(null);

  // 后台加载历史数据（不阻塞实时轮询）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [btcRes, ethRes] = await Promise.all([
          http.get('/prices/history', { params: { symbol: 'BTC_USDT', hours: 1 } }),
          http.get('/prices/history', { params: { symbol: 'ETH_USDT', hours: 1 } }),
        ]);
        if (cancelled) return;
        const btcHistory = (btcRes.data.data || []).map(p => ({ time: p.ts * 1000, BTC_USDT: p.price }));
        const ethHistory = (ethRes.data.data || []).map(p => ({ time: p.ts * 1000, ETH_USDT: p.price }));
        const merged = [];
        let bi = 0, ei = 0;
        while (bi < btcHistory.length || ei < ethHistory.length) {
          const bt = btcHistory[bi], et = ethHistory[ei];
          if (!bt) { merged.push(et); ei++; }
          else if (!et) { merged.push(bt); bi++; }
          else if (bt.time <= et.time) {
            merged.push({ ...bt, ETH_USDT: et.ETH_USDT });
            bi++; if (bt.time === et.time) ei++;
          } else { merged.push({ ...et, BTC_USDT: bt.BTC_USDT }); ei++; }
        }
        if (!cancelled) {
          setData(prev => {
            const prevTimes = new Set(prev.map(p => p.time));
            const newData = merged.filter(p => !prevTimes.has(p.time));
            return [...prev, ...newData].sort((a, b) => a.time - b.time).slice(-300);
          });
          const lastBtc = btcHistory[btcHistory.length - 1];
          const lastEth = ethHistory[ethHistory.length - 1];
          if (lastBtc || lastEth) {
            setMetrics(prev => ({
              BTC_USDT: lastBtc ? { price: lastBtc.BTC_USDT, change: '0.000' } : prev.BTC_USDT,
              ETH_USDT: lastEth ? { price: lastEth.ETH_USDT, change: '0.000' } : prev.ETH_USDT,
            }));
          }
        }
      } catch (_) {}
    })();
    return () => { cancelled = true; };
  }, []);

  // 实时轮询（立刻开始）
  useEffect(() => {
    const fetchPrices = async () => {
      try {
        const res = await getPrices();
        const prices = res.prices || {};
        const now = Date.now();
        setData(prev => {
          const next = [...prev, { time: now, BTC_USDT: prices.BTC_USDT, ETH_USDT: prices.ETH_USDT }];
          return next.slice(-300);
        });
        setMetrics(prev => {
          const btc = prices.BTC_USDT;
          const eth = prices.ETH_USDT;
          if (!btc && !eth) return prev;
          return {
            BTC_USDT: btc ? { price: btc, change: prev.BTC_USDT ? ((btc - prev.BTC_USDT.price) / prev.BTC_USDT.price * 100).toFixed(3) : '0.000' } : prev.BTC_USDT,
            ETH_USDT: eth ? { price: eth, change: prev.ETH_USDT ? ((eth - prev.ETH_USDT.price) / prev.ETH_USDT.price * 100).toFixed(3) : '0.000' } : prev.ETH_USDT,
          };
        });
      } catch (_) {}
    };
    fetchPrices();
    timerRef.current = setInterval(fetchPrices, 3000);
    return () => clearInterval(timerRef.current);
  }, []);

  const formatTime = (ts) => {
    const d = new Date(ts);
    return d.toLocaleTimeString();
  };

  const formatPrice = (val) => {
    if (val == null) return '—';
    return val >= 1000 ? val.toLocaleString(undefined, { maximumFractionDigits: 2 }) : val.toFixed(2);
  };

  return (
    <div>
      {/* 价格卡片 */}
      <div style={styles.cardRow}>
        {['BTC_USDT', 'ETH_USDT'].map(sym => {
          const m = metrics[sym];
          const change = parseFloat(m?.change || '0');
          return (
            <div key={sym} style={styles.priceCard}>
              <div style={styles.cardLabel}>{LABELS[sym]}</div>
              <div style={{ ...styles.cardPrice, color: COLORS[sym] }}>
                ${formatPrice(m?.price)}
              </div>
              <div style={{
                ...styles.cardChange,
                color: change >= 0 ? '#3fb950' : '#f85149',
              }}>
                {change >= 0 ? '↑' : '↓'} {Math.abs(change)}%
              </div>
            </div>
          );
        })}
      </div>

      {/* 走势图 */}
      <div style={styles.chartsGrid}>
        {['BTC_USDT', 'ETH_USDT'].map(sym => (
          <div key={sym} style={styles.chartBox}>
            <div style={styles.chartHeader}>
              <h3 style={{ ...styles.chartTitle, color: COLORS[sym] }}>{LABELS[sym]}</h3>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {data.length > 0 ? `$${data[data.length-1]?.[sym]?.toLocaleString(undefined,{minimumFractionDigits:1,maximumFractionDigits:1})}` : ''}
              </span>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={data}>
                <defs>
                  <linearGradient id={`grad_${sym}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={COLORS[sym]} stopOpacity={0.2}/>
                    <stop offset="100%" stopColor={COLORS[sym]} stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.05)" />
                <XAxis dataKey="time" tickFormatter={formatTime} stroke="#535c68" fontSize={10} tickLine={false} />
                <YAxis domain={['auto','auto']} stroke="#535c68" fontSize={10} tickFormatter={v=>v>=1000?(v/1000).toFixed(1)+'k':v.toFixed(0)} width={55} tickLine={false} />
                <Tooltip content={<ChartTooltip symbol={sym} />} />
                <Area type="monotone" dataKey={sym} fill={`url(#grad_${sym})`} stroke="none" isAnimationActive={false} />
                <Line type="monotone" dataKey={sym} stroke={COLORS[sym]} strokeWidth={2} dot={false} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ))}
      </div>

      <div style={styles.footnote}>
        实时数据来自 Gate.io · 2 秒刷新
      </div>
    </div>
  );
}

const styles = {
  cardRow: { display: 'flex', gap: 12, marginBottom: 16 },
  priceCard: {
    flex: 1, background: 'var(--bg-card)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)', padding: '20px 24px',
    boxShadow: 'var(--shadow-sm)', transition: 'border-color var(--transition)',
  },
  cardLabel: {
    fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)',
    textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 8,
  },
  cardPrice: {
    fontSize: 32, fontWeight: 700, fontFamily: 'var(--font-mono)', letterSpacing: '-.02em',
    lineHeight: 1.1,
  },
  cardChange: {
    fontSize: 13, marginTop: 8, fontFamily: 'var(--font-mono)', fontWeight: 500,
  },
  chartsGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 },
  chartBox: {
    background: 'var(--bg-card)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)', padding: 18, boxShadow: 'var(--shadow-sm)',
  },
  chartHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
    marginBottom: 8,
  },
  chartTitle: { fontSize: 12, fontWeight: 600 },
  footnote: {
    marginTop: 16, fontSize: 11, color: 'var(--text-muted)', textAlign: 'center',
    letterSpacing: '.02em',
  },
};
