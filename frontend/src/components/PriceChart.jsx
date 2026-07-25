import React, { useEffect, useState, useRef } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend
} from 'recharts';
import { getPrices } from '../api';

const COLORS = { BTC_USDT: '#f7931a', ETH_USDT: '#627eea' };
const LABELS = { BTC_USDT: 'BTC/USDT', ETH_USDT: 'ETH/USDT' };

export default function PriceChart() {
  const [data, setData] = useState([]);
  const [metrics, setMetrics] = useState({});
  const timerRef = useRef(null);

  useEffect(() => {
    const fetchPrices = async () => {
      try {
        const res = await getPrices();
        const prices = res.prices || {};
        const now = Date.now();
        setData(prev => {
          const next = [...prev, {
            time: now,
            BTC_USDT: prices.BTC_USDT,
            ETH_USDT: prices.ETH_USDT,
          }];
          return next.slice(-120); // 保留最近 120 个点（4 分钟）
        });

        // 更新指标
        setMetrics(prev => {
          const btc = prices.BTC_USDT;
          const eth = prices.ETH_USDT;
          if (!btc && !eth) return prev;
          return {
            BTC_USDT: btc ? { price: btc, change: prev.BTC_USDT ? ((btc - prev.BTC_USDT.price) / prev.BTC_USDT.price * 100).toFixed(3) : '0.000' } : prev.BTC_USDT,
            ETH_USDT: eth ? { price: eth, change: prev.ETH_USDT ? ((eth - prev.ETH_USDT.price) / prev.ETH_USDT.price * 100).toFixed(3) : '0.000' } : prev.ETH_USDT,
          };
        });
      } catch (_) {
        // 后端未启动时不报错
      }
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
