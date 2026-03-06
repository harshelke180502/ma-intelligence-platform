// Revenue stored in thousands USD (e.g. 6500 → $6.5M, 275000 → $275M)
const formatRevenue = (thousandsUSD) => {
  if (thousandsUSD == null) return '—'
  const millions = thousandsUSD / 1000
  if (millions >= 1000) return `$${(millions / 1000).toFixed(1)}B`
  return `$${millions.toFixed(1)}M`
}

const CARDS = (kpis) => [
  {
    label: 'Total Companies',
    value: kpis?.total_companies?.toLocaleString() ?? '—',
    sub: null,
  },
  {
    label: 'Ownership Identified',
    value: kpis ? `${kpis.pct_ownership_identified.toFixed(1)}%` : '—',
    sub: null,
  },
  {
    label: 'Avg Revenue Estimate',
    value: formatRevenue(kpis?.avg_revenue_est),
    sub: kpis
      ? `${kpis.enriched_revenue_count.toLocaleString()} of ${kpis.total_companies.toLocaleString()} enriched`
      : null,
  },
  {
    label: 'Companies Excluded',
    value: kpis?.companies_excluded?.toLocaleString() ?? '—',
    sub: null,
  },
]

export default function KpiCards({ kpis, loading }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {CARDS(kpis).map(({ label, value, sub }) => (
        <div key={label} className="bg-white rounded-lg border border-gray-200 p-5">
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-2xl font-semibold text-gray-900 mt-1">
            {loading ? <span className="text-gray-300">—</span> : value}
          </p>
          {sub && !loading && (
            <p className="text-xs text-gray-400 mt-1">{sub}</p>
          )}
        </div>
      ))}
    </div>
  )
}
