import { useState, useEffect, useCallback } from 'react'
import { fetchCompanies, enrichCompany as apiEnrichCompany } from '../api/client'

const SERVICE_OPTIONS = [
  { value: '', label: 'All Services' },
  { value: 'rd_credits', label: 'R&D Credits' },
  { value: 'cost_seg', label: 'Cost Seg' },
  { value: 'wotc', label: 'WOTC' },
  { value: 'sales_use_tax', label: 'Sales & Use Tax' },
]

const SERVICE_LABELS = {
  rd_credits: 'R&D Credits',
  cost_seg: 'Cost Seg',
  wotc: 'WOTC',
  sales_use_tax: 'Sales & Use Tax',
}

const SERVICE_COLORS = {
  rd_credits: 'bg-blue-100 text-blue-700',
  cost_seg: 'bg-green-100 text-green-700',
  wotc: 'bg-amber-100 text-amber-700',
  sales_use_tax: 'bg-purple-100 text-purple-700',
}

const OWNERSHIP_LABELS = {
  private: 'Private',
  pe_backed: 'PE-Backed',
  public: 'Public',
  franchise: 'Franchise',
}

const OWNERSHIP_COLORS = {
  private: 'bg-gray-100 text-gray-600',
  pe_backed: 'bg-violet-100 text-violet-700',
  public: 'bg-emerald-100 text-emerald-700',
  franchise: 'bg-orange-100 text-orange-700',
}

// Revenue is stored in thousands USD (e.g. 6500 = $6.5M, 275000 = $275M)
function formatRevenue(min, max) {
  if (min == null && max == null) return '—'
  const avgK = ((min ?? 0) + (max ?? min ?? 0)) / 2  // thousands USD
  const avgM = avgK / 1000                             // millions USD
  if (avgM >= 1000) return `$${(avgM / 1000).toFixed(1)}B`
  return `$${avgM.toFixed(1)}M`
}

function ThesisBadge({ score }) {
  if (score == null) return <span className="text-gray-300">—</span>
  const pct = Math.round(score * 100)
  const color =
    pct >= 70 ? 'bg-green-100 text-green-700' :
    pct >= 40 ? 'bg-amber-100 text-amber-700' :
                'bg-red-100 text-red-700'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${color}`}>
      {pct}%
    </span>
  )
}

function SortIcon({ col, sort, order }) {
  if (sort !== col) return <span className="text-gray-300 ml-1">↕</span>
  return <span className="ml-1 text-gray-700">{order === 'asc' ? '↑' : '↓'}</span>
}

export default function CompaniesTable({ onSelectCompany }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [service, setService] = useState('')
  const [sort, setSort] = useState('name')
  const [order, setOrder] = useState('asc')
  const [page, setPage] = useState(1)
  const [enrichingId, setEnrichingId] = useState(null)
  const limit = 50

  const load = useCallback(() => {
    setLoading(true)
    const params = { sort, order, page, limit }
    if (service) params.service = service
    fetchCompanies(params)
      .then(setData)
      .finally(() => setLoading(false))
  }, [service, sort, order, page])

  useEffect(() => { load() }, [load])

  const handleSort = (col) => {
    if (sort === col) {
      setOrder((o) => (o === 'asc' ? 'desc' : 'asc'))
    } else {
      setSort(col)
      setOrder('asc')
    }
    setPage(1)
  }

  const handleServiceChange = (e) => {
    setService(e.target.value)
    setPage(1)
  }

  const handleEnrich = (e, companyId) => {
    e.stopPropagation()
    setEnrichingId(companyId)
    apiEnrichCompany(companyId)
      .then(() => load())
      .finally(() => setEnrichingId(null))
  }

  const thClass = 'px-4 py-3 font-medium text-gray-600 cursor-pointer select-none whitespace-nowrap'
  const tdClass = 'px-4 py-3'

  return (
    <div className="bg-white rounded-lg border border-gray-200">
      {/* Header row */}
      <div className="px-5 py-4 flex items-center justify-between border-b border-gray-200 gap-4">
        <h2 className="text-sm font-medium text-gray-700 shrink-0">
          Companies
          {data && (
            <span className="ml-2 text-gray-400 font-normal">
              ({data.total.toLocaleString()} total)
            </span>
          )}
        </h2>
        <select
          className="text-sm border border-gray-200 rounded-md px-3 py-1.5 text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={service}
          onChange={handleServiceChange}
        >
          {SERVICE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-left">
              <th className={thClass} onClick={() => handleSort('name')}>
                Company <SortIcon col="name" sort={sort} order={order} />
              </th>
              <th className={`${thClass} w-16`} onClick={() => handleSort('state')}>
                State <SortIcon col="state" sort={sort} order={order} />
              </th>
              <th className={`${thClass} cursor-default`}>Services</th>
              <th className={`${thClass} cursor-default`}>Website</th>
              <th className={`${thClass} cursor-default`} onClick={() => handleSort('ownership_type')}>
                Ownership <SortIcon col="ownership_type" sort={sort} order={order} />
              </th>
              <th className={`${thClass} cursor-default`} onClick={() => handleSort('revenue_est_min')}>
                Avg Revenue <SortIcon col="revenue_est_min" sort={sort} order={order} />
              </th>
              <th className={`${thClass} cursor-default`} onClick={() => handleSort('thesis_fit_score')}>
                Thesis Fit <SortIcon col="thesis_fit_score" sort={sort} order={order} />
              </th>
              <th className={`${thClass} cursor-default w-24`}></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="px-5 py-12 text-center text-gray-400">
                  Loading...
                </td>
              </tr>
            ) : !data?.items.length ? (
              <tr>
                <td colSpan={8} className="px-5 py-12 text-center text-gray-400">
                  No companies found.
                </td>
              </tr>
            ) : (
              data.items.map((company) => (
                <tr
                  key={company.id}
                  className="border-b border-gray-100 last:border-0 hover:bg-gray-50 cursor-pointer"
                  onClick={() => onSelectCompany(company.id)}
                >
                  <td className={`${tdClass} font-medium text-gray-900`}>{company.name}</td>
                  <td className={`${tdClass} text-gray-600`}>{company.state ?? '—'}</td>
                  <td className={tdClass}>
                    <div className="flex flex-wrap gap-1">
                      {(company.services ?? []).map((svc) => (
                        <span
                          key={svc}
                          className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                            SERVICE_COLORS[svc] ?? 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          {SERVICE_LABELS[svc] ?? svc}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className={`${tdClass} text-gray-500`}>
                    {company.website ? (
                      <a
                        href={`https://${company.website}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {company.website}
                      </a>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className={tdClass}>
                    {company.ownership_type ? (
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        OWNERSHIP_COLORS[company.ownership_type] ?? 'bg-gray-100 text-gray-600'
                      }`}>
                        {OWNERSHIP_LABELS[company.ownership_type] ?? company.ownership_type}
                      </span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className={`${tdClass} text-gray-600`}>
                    {formatRevenue(company.revenue_est_min, company.revenue_est_max)}
                  </td>
                  <td className={tdClass}>
                    <ThesisBadge score={company.thesis_fit_score} />
                  </td>
                  <td className={tdClass} onClick={(e) => e.stopPropagation()}>
                    <button
                      disabled={enrichingId === company.id}
                      onClick={(e) => handleEnrich(e, company.id)}
                      className="px-3 py-1 text-xs rounded border border-gray-200 text-gray-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
                    >
                      {enrichingId === company.id ? 'Enriching…' : 'Enrich'}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="px-5 py-3 flex items-center justify-between border-t border-gray-200">
          <span className="text-sm text-gray-500">
            Page {data.page} of {data.pages}
          </span>
          <div className="flex gap-2">
            <button
              disabled={data.page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1 text-sm rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              disabled={data.page >= data.pages}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 text-sm rounded border border-gray-200 disabled:opacity-40 hover:bg-gray-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
