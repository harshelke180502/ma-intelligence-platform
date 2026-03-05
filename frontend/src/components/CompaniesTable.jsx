import { useState, useEffect, useCallback } from 'react'
import { fetchCompanies } from '../api/client'

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

  const thClass = 'px-5 py-3 font-medium text-gray-600 cursor-pointer select-none whitespace-nowrap'
  const tdClass = 'px-5 py-3'

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
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-5 py-12 text-center text-gray-400">
                  Loading...
                </td>
              </tr>
            ) : !data?.items.length ? (
              <tr>
                <td colSpan={4} className="px-5 py-12 text-center text-gray-400">
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
                      '—'
                    )}
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
