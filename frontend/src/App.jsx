import React, { useState, useCallback, useEffect, Suspense, lazy } from 'react';
import { getPrices } from './api';

// ═══ Lazy-load tab components for code splitting ═══
// Recharts (~150KB+) is only loaded when a chart tab is first visited
const PriceChart = lazy(() => import('./components/PriceChart'));
const BacktestPanel = lazy(() => import('./components/BacktestPanel'));
const StrategyTrace = lazy(() => import('./components/StrategyTrace'));
const SimAccount = lazy(() => import('./components/SimAccount'));

const TABS = [
  { key: 'dashboard', label: '行情看板', icon: '📊' },
  { key: 'backtest', label: '回测引擎', icon: '🔬' },
  { key: 'trace', label: '策略溯源', icon: '🔍' },
  { key: 'account', label: '模拟账户', icon: '💰' },
];

const TabLoading = () => (
  <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)', fontSize: 15 }}>
    <div style={{ fontSize: 32, marginBottom: 12 }}>⏳</div>
    <div>加载模块中...</div>
  </div>
);

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [traceReport, setTraceReport] = useState(null);
  const [headerData, setHeaderData] = useState({ btc: null, eth: null, source: 'SIMULATED' });
  // Track which tabs have been loaded at least once (keep-alive pattern)
  const [loadedTabs, setLoadedTabs] = useState(new Set(['dashboard']));

  useEffect(() => {
    const iv = setInterval(async () => {
      try {
        const res = await getPrices();
        if (res) {
          setHeaderData(prev => {
            const btc = res.prices?.BTC_USDT;
            const eth = res.prices?.ETH_USDT;
            const source = res.data_source?.source || 'SIMULATED';
            // Skip update if prices haven't changed (reduce re-renders)
            if (btc === prev.btc && eth === prev.eth && source === prev.source) return prev;
            return { btc, eth, source };
          });
        }
      } catch (_) {}
    }, 3000);
    return () => clearInterval(iv);
  }, []);

  const switchTab = useCallback((key) => {
    setLoadedTabs(prev => {
      if (prev.has(key)) return prev;
      return new Set([...prev, key]);
    });
    setActiveTab(key);
  }, []);

  const handleTrace = useCallback((report) => {
    setTraceReport(report);
    switchTab('trace');
  }, [switchTab]);

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
              background: isLive ? 'var(--accent)' : 'var(--text-muted)',
              boxShadow: isLive ? '0 0 6px rgba(212,168,83,.5)' : 'none',
              animation: isLive ? 'pulse 2s infinite' : 'none',
            }} />
            <span style={{ color: isLive ? 'var(--accent)' : 'var(--text-muted)', fontSize: 11, fontWeight: 600 }}>
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
            onClick={() => switchTab(t.key)}
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

      {/* ═══════ Content: lazy-loaded + keep-alive (hidden tabs stay mounted) ═══════ */}
      <main style={styles.main}>
        <Suspense fallback={<TabLoading />}>
          <div style={{ display: activeTab === 'dashboard' ? 'block' : 'none' }}>
            {loadedTabs.has('dashboard') && <PriceChart active={activeTab === 'dashboard'} />}
          </div>
          <div style={{ display: activeTab === 'backtest' ? 'block' : 'none' }}>
            {loadedTabs.has('backtest') && <BacktestPanel onTrace={handleTrace} active={activeTab === 'backtest'} />}
          </div>
          <div style={{ display: activeTab === 'trace' ? 'block' : 'none' }}>
            {loadedTabs.has('trace') && <StrategyTrace report={traceReport} active={activeTab === 'trace'} />}
          </div>
          <div style={{ display: activeTab === 'account' ? 'block' : 'none' }}>
            {loadedTabs.has('account') && <SimAccount active={activeTab === 'account'} />}
          </div>
        </Suspense>
      </main>
    </div>
  );
}

const styles = {
  wrapper: { minHeight: '100vh', maxWidth: 1200, margin: '0 auto', padding: '0 20px 40px' },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '18px 0 12px', borderBottom: '1px solid var(--border)',
    flexWrap: 'wrap', gap: 10,
  },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 10 },
  title: { fontSize: 17, fontWeight: 600, color: 'var(--accent)', letterSpacing: '-.01em' },
  sourceBadge: {
    display: 'flex', alignItems: 'center', gap: 5,
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 20, padding: '2px 9px',
  },
  dot: { width: 6, height: 6, borderRadius: '50%' },
  headerRight: { display: 'flex', gap: 12 },
  ticker: { display: 'flex', alignItems: 'baseline', gap: 5 },
  tickerLabel: { fontSize: 9, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.06em' },
  tickerPrice: { fontSize: 13, fontWeight: 600, color: 'var(--accent)', fontFamily: 'var(--font-mono)' },
  tabs: { display: 'flex', gap: 2, padding: '12px 0', borderBottom: '1px solid var(--border)' },
  tab: {
    display: 'flex', alignItems: 'center', gap: 5,
    padding: '6px 16px', border: '1px solid transparent', borderRadius: 'var(--radius-lg)',
    background: 'transparent', color: 'var(--text-secondary)',
    fontSize: 12, fontWeight: 500,
  },
  tabActive: {
    background: 'rgba(255,255,255,.05)', border: '1px solid var(--border)',
    color: 'var(--accent)',
  },
  main: { paddingTop: 16 },
};

export default App;
