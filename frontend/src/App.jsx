import React, { useState, useCallback, useEffect } from 'react';
import PriceChart from './components/PriceChart';
import BacktestPanel from './components/BacktestPanel';
import StrategyTrace from './components/StrategyTrace';
import SimAccount from './components/SimAccount';
import { getPrices } from './api';

const TABS = [
  { key: 'dashboard', label: '行情看板', icon: '📊' },
  { key: 'backtest', label: '回测引擎', icon: '🔬' },
  { key: 'trace', label: '策略溯源', icon: '🔍' },
  { key: 'account', label: '模拟账户', icon: '💰' },
];

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [traceReport, setTraceReport] = useState(null);
  const [headerData, setHeaderData] = useState({ btc: null, eth: null, source: 'SIMULATED' });

  useEffect(() => {
    const iv = setInterval(async () => {
      try {
        const res = await getPrices();
        if (res) {
          setHeaderData({
            btc: res.prices?.BTC_USDT,
            eth: res.prices?.ETH_USDT,
            source: res.data_source?.source || 'SIMULATED',
          });
        }
      } catch (_) {}
    }, 2000);
    return () => clearInterval(iv);
  }, []);

  const handleTrace = useCallback((report) => {
    setTraceReport(report);
    setActiveTab('trace');
  }, []);

  const isLive = headerData.source === 'LIVE';

  return (
    <div style={styles.wrapper}>
      {/* ═══════ Header ═══════ */}
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <h1 style={styles.title}>事件合约模拟交易系统</h1>
          <div style={styles.sourceBadge}>
            <span style={{
              ...styles.dot,
              background: isLive ? '#3fb950' : '#d29922',
              boxShadow: isLive ? '0 0 6px #3fb95088' : '0 0 6px #d2992288',
              animation: isLive ? 'pulse 2s infinite' : 'none',
            }} />
            <span style={{ color: isLive ? '#3fb950' : '#d29922', fontSize: 11, fontWeight: 600 }}>
              {isLive ? 'LIVE' : 'SIM'}
            </span>
          </div>
        </div>
        <div style={styles.headerRight}>
          {headerData.btc && (
            <div style={styles.ticker}>
              <span style={styles.tickerLabel}>BTC</span>
              <span style={{ ...styles.tickerPrice, fontFamily: 'var(--font-mono)' }}>
                ${headerData.btc.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
              </span>
            </div>
          )}
          {headerData.eth && (
            <div style={styles.ticker}>
              <span style={styles.tickerLabel}>ETH</span>
              <span style={{ ...styles.tickerPrice, fontFamily: 'var(--font-mono)' }}>
                ${headerData.eth.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}
              </span>
            </div>
          )}
        </div>
      </header>

      {/* ═══════ Tabs ═══════ */}
      <nav style={styles.tabs}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              ...styles.tab,
              ...(activeTab === t.key ? styles.tabActive : {}),
            }}
          >
            <span style={{ fontSize: 15 }}>{t.icon}</span>
            {t.label}
          </button>
        ))}
      </nav>

      {/* ═══════ Content ═══════ */}
      <main style={styles.main}>
        {activeTab === 'dashboard' && <PriceChart />}
        {activeTab === 'backtest' && <BacktestPanel onTrace={handleTrace} />}
        {activeTab === 'trace' && <StrategyTrace report={traceReport} />}
        {activeTab === 'account' && <SimAccount />}
      </main>
    </div>
  );
}

const styles = {
  wrapper: { minHeight: '100vh', maxWidth: 1440, margin: '0 auto', padding: '0 24px 40px' },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '20px 0 14px', borderBottom: '1px solid var(--border)',
    flexWrap: 'wrap', gap: 12,
  },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 12 },
  title: { fontSize: 20, fontWeight: 700, color: '#e6edf3', letterSpacing: '-0.01em' },
  sourceBadge: {
    display: 'flex', alignItems: 'center', gap: 5,
    background: 'var(--bg-card)', border: '1px solid var(--border)',
    borderRadius: 20, padding: '3px 10px',
  },
  dot: { width: 7, height: 7, borderRadius: '50%' },
  headerRight: { display: 'flex', gap: 14 },
  ticker: { display: 'flex', alignItems: 'baseline', gap: 6 },
  tickerLabel: { fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' },
  tickerPrice: { fontSize: 14, fontWeight: 600, color: '#e6edf3' },
  tabs: {
    display: 'flex', gap: 4, padding: '14px 0',
    borderBottom: '1px solid var(--border)',
  },
  tab: {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '8px 18px', border: '1px solid transparent', borderRadius: 'var(--radius)',
    background: 'transparent', color: 'var(--text-secondary)',
    fontSize: 13, fontWeight: 500,
  },
  tabActive: {
    background: 'var(--accent-dim)', border: '1px solid rgba(47,129,247,.25)',
    color: 'var(--accent)',
  },
  main: { paddingTop: 20 },
};

export default App;
