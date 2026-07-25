import React, { useEffect, useState, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend
} from 'recharts';
import { getPrices } from '../api';
import axios from 'axios';

const API = process.env.REACT_APP_API ?? '';
const http = axios.create({ baseURL: API, timeout: 30000 });

const COLORS = { BTC_USDT: '#f7931a', ETH_USDT: '#627eea' };
const LABELS = { BTC_USDT: 'BTC/USDT', ETH_USDT: 'ETH/USDT' };

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
    timerRef.current = setInterval(fetchPrices, 2000);
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
            <h3 style={{ ...styles.chartTitle, color: COLORS[sym] }}>{LABELS[sym]}</h3>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
                <XAxis
                  dataKey="time"
                  tickFormatter={formatTime}
                  stroke="#484f58"
                  fontSize={11}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  stroke="#484f58"
                  fontSize={11}
                  tickFormatter={formatPrice}
                  width={70}
                />
                <Tooltip
                  contentStyle={{
                    background: '#161b22',
                    border: '1px solid #30363d',
                    borderRadius: 6,
                    fontSize: 13,
                  }}
                  labelFormatter={formatTime}
                  formatter={(val) => ['$' + formatPrice(val), LABELS[sym]]}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey={sym}
                  name={LABELS[sym]}
                  stroke={COLORS[sym]}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
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
  cardRow: {
    display: 'flex',
    gap: 16,
    marginBottom: 20,
  },
  priceCard: {
    flex: 1,
    background: '#161b22',
    border: '1px solid #21262d',
    borderRadius: 8,
    padding: '16px 20px',
  },
  cardLabel: {
    fontSize: 12,
    color: '#8b949e',
    marginBottom: 4,
  },
  cardPrice: {
    fontSize: 28,
    fontWeight: 700,
    fontFamily: 'monospace',
  },
  cardChange: {
    fontSize: 13,
    marginTop: 4,
    fontFamily: 'monospace',
  },
  chartsGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 20,
  },
  chartBox: {
    background: '#161b22',
    border: '1px solid #21262d',
    borderRadius: 8,
    padding: 16,
  },
  chartTitle: {
    fontSize: 14,
    fontWeight: 600,
    marginBottom: 12,
  },
  footnote: {
    marginTop: 12,
    fontSize: 11,
    color: '#484f58',
    textAlign: 'center',
  },
};
