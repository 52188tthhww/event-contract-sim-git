import React, { useMemo, memo } from 'react';
import {
  ComposedChart, Line, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine, Area, Legend
} from 'recharts';

const StrategyTrace = memo(function StrategyTrace({ report }) {
  if (!report) {
    return (
      <div style={styles.empty}>
        <div style={styles.emptyIcon}>🔍</div>
        <div style={styles.emptyTitle}>策略溯源</div>
        <div style={styles.emptyDesc}>
          在回测引擎中点击策略的「溯源」按钮<br />
          可查看完整开仓节点与精准入场点位
        </div>
      </div>
    );
  }

  const toLocalShort = (isoStr) => {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    const ss = String(d.getSeconds()).padStart(2, '0');
    return `${mm}-${dd} ${hh}:${min}:${ss}`;
  };

  // 构建图表数据：每笔交易 + 累计盈亏
  const chartData = useMemo(() => {
    let cumPnl = 0;
    return report.trades.slice(-60).map((t, i) => {
      cumPnl += t.pnl;
      return {
        index: i + 1,
        pnl: parseFloat(t.pnl.toFixed(4)),
        cumPnl: parseFloat(cumPnl.toFixed(4)),
        result: t.result,
        direction: t.direction,
        entryPrice: t.entry_price,
        exitPrice: t.exit_price,
        entryTime: toLocalShort(t.entry_time),
        reason: t.reason,
      };
    });
  }, [report.trades]);

  const wins = report.trades.filter(t => t.result === 'WIN');
  const losses = report.trades.filter(t => t.result === 'LOSE');
  const maxWin = wins.length > 0 ? Math.max(...wins.map(t => t.pnl)) : 0;
  const maxLoss = losses.length > 0 ? Math.min(...losses.map(t => t.pnl)) : 0;

  const formatPrice = (v) => {
    if (v == null) return '—';
    return v.toFixed(4);
  };
  // 暗色主题 tooltip
  const tooltipStyle = {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    fontSize: 12,
    color: 'var(--text)',
  };

  return (
    <div>
      {/* ═══════ 概览卡片 ═══════ */}
      <div style={styles.overviewGrid}>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>策略</div>
          <div style={styles.statValue}>{report.strategy_name}</div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>合约时长</div>
          <div style={styles.statValue}>{report.duration} 分钟</div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>胜率</div>
          <div style={{ ...styles.statValue, color: report.win_rate >= 0.75 ? 'var(--text)' : 'var(--text-secondary)' }}>
            {(report.win_rate * 100).toFixed(1)}%
          </div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>总交易</div>
          <div style={styles.statValue}>
            {report.total_trades}
            <span style={{ fontSize: 12, marginLeft: 8 }}>
              ✅{report.wins} ❌{report.losses}
            </span>
          </div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>净盈亏</div>
          <div style={{
            ...styles.statValue,
            color: report.net_pnl >= 0 ? 'var(--text)' : 'var(--down)',
          }}>
            {report.net_pnl >= 0 ? '+' : ''}{report.net_pnl.toFixed(4)}
          </div>
        </div>
        <div style={styles.statCard}>
          <div style={styles.statLabel}>期望值 / 盈亏比</div>
          <div style={styles.statValue}>
            {report.expectancy.toFixed(4)}
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              {' '}| {report.avg_win > 0 && report.avg_loss < 0
                ? (report.avg_win / Math.abs(report.avg_loss)).toFixed(2)
                : '—'}
            </span>
          </div>
        </div>
      </div>

      {/* ═══════ 图表双栏 ═══════ */}
      <div style={styles.chartsRow}>
        {/* 累计盈亏曲线 */}
        <div style={styles.chartBox}>
          <h3 style={styles.chartTitle}>📈 累计盈亏曲线</h3>
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis
                dataKey="index"
                stroke="#484f58"
                fontSize={11}
                label={{ value: '交易序号', position: 'bottom', fill: 'var(--text-secondary)', fontSize: 11, offset: -5 }}
              />
              <YAxis
                stroke="#484f58"
                fontSize={11}
                tickFormatter={v => v.toFixed(0)}
                width={60}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(val, name) => {
                  if (name === '累计盈亏') return [`$${val.toFixed(4)}`, '累计盈亏'];
                  if (name === '单笔盈亏') return [`$${val.toFixed(4)}`, '单笔盈亏'];
                  return [val, name];
                }}
                labelFormatter={(idx) => {
                  const d = chartData[idx - 1];
                  if (!d) return `#${idx}`;
                  return `#${idx} ${d.entryTime} ${d.direction}`;
                }}
              />
              <ReferenceLine y={0} stroke="#484f58" strokeDasharray="4 4" />
              <Area
                type="monotone"
                dataKey="cumPnl"
                name="累计盈亏"
                fill="#3fb95022"
                stroke="#3fb950"
                strokeWidth={2}
                dot={false}
              />
              <Bar
                dataKey="pnl"
                name="单笔盈亏"
                fill="#8884d8"
                opacity={0.6}
                radius={[2, 2, 0, 0]}
              >
                {chartData.map((d, i) => (
                  <rect
                    key={i}
                    fill={d.result === 'WIN' ? 'var(--text)' : 'var(--down)'}
                    opacity={0.7}
                  />
                ))}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
          <div style={styles.chartLegend}>
            <span>🟢 盈利 ({wins.length})</span>
            <span>🔴 亏损 ({losses.length})</span>
            <span>最大盈利: +{maxWin.toFixed(4)}</span>
            <span>最大亏损: {maxLoss.toFixed(4)}</span>
            <span>累计: {report.net_pnl >= 0 ? '+' : ''}{report.net_pnl.toFixed(4)}</span>
          </div>
        </div>

        {/* 入场价 vs 出场价 对比 */}
        <div style={styles.chartBox}>
          <h3 style={styles.chartTitle}>📍 入场 & 出场价格对比</h3>
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis
                dataKey="index"
                stroke="#484f58"
                fontSize={11}
                label={{ value: '交易序号', position: 'bottom', fill: 'var(--text-secondary)', fontSize: 11, offset: -5 }}
              />
              <YAxis
                stroke="#484f58"
                fontSize={11}
                tickFormatter={v => v.toFixed(1)}
                width={70}
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(val, name) => [`$${formatPrice(val)}`, name]}
                labelFormatter={(idx) => {
                  const d = chartData[idx - 1];
                  return d ? `#${idx} ${d.entryTime}` : `#${idx}`;
                }}
              />
              <Line
                type="monotone"
                dataKey="entryPrice"
                name="入场价"
                stroke="#58a6ff"
                strokeWidth={1.5}
                dot={{ r: 3, fill: 'var(--text)' }}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="exitPrice"
                name="出场价"
                stroke="#d29922"
                strokeWidth={1.5}
                dot={{ r: 3, fill: 'var(--text-secondary)' }}
                connectNulls
              />
              <Legend
                wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 11 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ═══════ 交易明细表 ═══════ */}
      <div style={styles.tableBox}>
        <h3 style={styles.chartTitle}>
          📋 全部开仓节点与入场点位
          <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 12 }}>
            共 {report.total_trades} 笔
          </span>
        </h3>
        <div style={styles.scrollTable}>
          <table style={styles.table}>
            <thead>
              <tr style={styles.tableHeaderRow}>
                <th style={styles.th}>#</th>
                <th style={styles.th}>入场时间</th>
                <th style={styles.th}>方向</th>
                <th style={styles.th}>入场价</th>
                <th style={styles.th}>出场时间</th>
                <th style={styles.th}>出场价</th>
                <th style={styles.th}>盈亏</th>
                <th style={styles.th}>盈亏%</th>
                <th style={styles.th}>结果</th>
                <th style={styles.th}>触发原因</th>
              </tr>
            </thead>
            <tbody>
              {report.trades.map((t, i) => (
                <tr key={i} style={t.result === 'WIN' ? styles.winRow : styles.lossRow}>
                  <td style={styles.td}>{i + 1}</td>
                  <td style={styles.td}>{toLocalShort(t.entry_time)}</td>
                  <td style={styles.td}>
                    <span style={{
                      color: t.direction === 'UP' ? 'var(--text)' : 'var(--down)',
                      fontWeight: 600,
                    }}>
                      {t.direction === 'UP' ? '📈 看涨' : '📉 看跌'}
                    </span>
                  </td>
                  <td style={{ ...styles.td, fontFamily: 'var(--font-mono)' }}>${formatPrice(t.entry_price)}</td>
                  <td style={styles.td}>{toLocalShort(t.exit_time)}</td>
                  <td style={{ ...styles.td, fontFamily: 'var(--font-mono)' }}>${formatPrice(t.exit_price)}</td>
                  <td style={{
                    ...styles.td,
                    fontFamily: 'var(--font-mono)',
                    color: t.pnl >= 0 ? 'var(--text)' : 'var(--down)',
                    fontWeight: 600,
                  }}>
                    {t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(4)}
                  </td>
                  <td style={{
                    ...styles.td,
                    fontFamily: 'var(--font-mono)',
                    color: t.pnl_pct >= 0 ? 'var(--text)' : 'var(--down)',
                  }}>
                    {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(4)}%
                  </td>
                  <td style={styles.td}>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: 10,
                      fontSize: 11,
                      fontWeight: 600,
                      background: t.result === 'WIN' ? 'var(--accent-dim)' : 'rgba(255,255,255,.03)',
                      color: t.result === 'WIN' ? 'var(--text)' : 'var(--down)',
                    }}>
                      {t.result === 'WIN' ? '✅ WIN' : '❌ LOSE'}
                    </span>
                  </td>
                  <td style={{ ...styles.td, fontSize: 11, color: 'var(--text-secondary)', maxWidth: 260 }}>
                    {t.reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
});

export default StrategyTrace;

const styles = {
  empty: {
    textAlign: 'center',
    padding: 80,
    color: 'var(--text-muted)',
  },
  emptyIcon: { fontSize: 48, marginBottom: 16 },
  emptyTitle: { fontSize: 18, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 },
  emptyDesc: { fontSize: 14, lineHeight: '1.8' },

  // 概览卡片
  overviewGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(6, 1fr)',
    gap: 12,
    marginBottom: 20,
  },
  statCard: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 16px',
  },
  statLabel: { fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 },
  statValue: { fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)' },

  // 图表双栏
  chartsRow: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 16,
    marginBottom: 20,
  },
  chartBox: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: 20,
  },
  chartTitle: {
    fontSize: 14,
    fontWeight: 600,
    marginBottom: 12,
    color: 'var(--text)',
  },
  chartLegend: {
    display: 'flex',
    gap: 16,
    justifyContent: 'center',
    flexWrap: 'wrap',
    fontSize: 12,
    color: 'var(--text-secondary)',
    marginTop: 8,
  },

  // 明细表
  tableBox: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: 20,
  },
  scrollTable: {
    maxHeight: 500,
    overflowY: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 12,
    color: 'var(--text)',
  },
  tableHeaderRow: {
    position: 'sticky',
    top: 0,
    background: 'var(--bg)',
    zIndex: 1,
  },
  th: {
    padding: '8px 12px',
    textAlign: 'left',
    borderBottom: '1px solid #30363d',
    color: 'var(--text-secondary)',
    fontWeight: 600,
    fontSize: 11,
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '6px 12px',
    borderBottom: '1px solid #21262d',
    whiteSpace: 'nowrap',
  },
  winRow: {},
  lossRow: { opacity: 0.65 },
};
