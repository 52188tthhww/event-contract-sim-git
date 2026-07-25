import React, { useState, useCallback } from 'react';
import PriceChart from './components/PriceChart';
import BacktestPanel from './components/BacktestPanel';
import StrategyTrace from './components/StrategyTrace';
import SimAccount from './components/SimAccount';

const TABS = [
  { key: 'dashboard', label: '📊 行情看板' },
  { key: 'backtest', label: '🔬 回测引擎' },
  { key: 'trace', label: '🔍 策略溯源' },
  { key: 'account', label: '💰 模拟账户' },
];

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [traceReport, setTraceReport] = useState(null);

  const handleTrace = useCallback((report) => {
    setTraceReport(report);
    setActiveTab('trace');
  }, []);

  return (
    <div style={styles.wrapper}>
      {/* 顶栏 */}
      <header style={styles.header}>
        <h1 style={styles.title}>📈 事件合约模拟交易系统</h1>
        <span style={styles.subtitle}>3m / 5m / 10m | Gate.io | ≥75% 胜率筛选</span>
      </header>

      {/* 标签页 */}
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
            {t.label}
          </button>
        ))}
      </nav>

      {/* 内容区 */}
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
  wrapper: {
    minHeight: '100vh',
    maxWidth: 1400,
    margin: '0 auto',
    padding: '0 20px 40px',
  },
  header: {
    padding: '24px 0 12px',
    borderBottom: '1px solid #21262d',
    display: 'flex',
    alignItems: 'baseline',
    gap: 16,
  },
  title: {
    fontSize: 22,
    fontWeight: 700,
    color: '#58a6ff',
  },
  subtitle: {
    fontSize: 13,
    color: '#8b949e',
  },
  tabs: {
    display: 'flex',
    gap: 4,
    padding: '16px 0',
    borderBottom: '1px solid #21262d',
  },
  tab: {
    padding: '8px 20px',
    border: 'none',
    borderRadius: 6,
    background: 'transparent',
    color: '#8b949e',
    fontSize: 14,
    fontWeight: 500,
    transition: 'all 0.15s',
  },
  tabActive: {
    background: '#1f6feb33',
    color: '#58a6ff',
  },
  main: {
    paddingTop: 20,
  },
};

export default App;
