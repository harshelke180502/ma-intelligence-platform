// formatRevenue: revenue is stored in thousands USD (6500 → $6.5M)
const formatRevenue = (thousandsUSD) => {
  if (thousandsUSD == null) return '—'
  return `$${(thousandsUSD / 1000).toFixed(1)}M`
}

const CARDS = (kpis) => [
  {
    label: 'Total Companies',
    value: kpis?.total_companies?.toLocaleString() ?? '—',
  },
  {
    label: 'Ownership Identified',
    value: kpis ? `${kpis.pct_ownership_identified.toFixed(1)}%` : '—',
  },
  {
    label: 'Avg Revenue Estimate',
    value: formatRevenue(kpis?.avg_revenue_est),
  },
  {
    label: 'Companies Excluded',
    value: kpis?.companies_excluded?.toLocaleString() ?? '—',
  },
]

export default function KpiCards({ kpis, loading }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {CARDS(kpis).map(({ label, value }) => (
        <div key={label} className="bg-white rounded-lg border border-gray-200 p-5">
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-2xl font-semibold text-gray-900 mt-1">
            {loading ? <span className="text-gray-300">—</span> : value}
          </p>
        </div>
      ))}
    </div>
  )
}
