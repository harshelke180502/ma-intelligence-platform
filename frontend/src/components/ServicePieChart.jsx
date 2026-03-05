import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

const SERVICE_LABELS = {
  rd_credits: 'R&D Credits',
  cost_seg: 'Cost Seg',
  wotc: 'WOTC',
  sales_use_tax: 'Sales & Use Tax',
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6']

const RADIAN = Math.PI / 180
const renderInnerLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }) => {
  if (percent < 0.06) return null
  const r = innerRadius + (outerRadius - innerRadius) * 0.55
  const x = cx + r * Math.cos(-midAngle * RADIAN)
  const y = cy + r * Math.sin(-midAngle * RADIAN)
  return (
    <text
      x={x}
      y={y}
      fill="white"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={12}
      fontWeight={600}
    >
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  )
}

export default function ServicePieChart({ data, loading }) {
  const chartData = data
    ? Object.entries(data).map(([key, value]) => ({
        name: SERVICE_LABELS[key] ?? key,
        value,
      }))
    : []

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h2 className="text-sm font-medium text-gray-700 mb-4">Service Distribution</h2>
      {loading || !chartData.length ? (
        <div className="h-64 flex items-center justify-center text-gray-400 text-sm">
          Loading...
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              outerRadius={95}
              dataKey="value"
              labelLine={false}
              label={renderInnerLabel}
            >
              {chartData.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(v) => v.toLocaleString()} />
            <Legend
              iconType="circle"
              iconSize={8}
              formatter={(value) => (
                <span className="text-xs text-gray-600">{value}</span>
              )}
            />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
