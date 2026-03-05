import { useState, useEffect } from 'react'
import { fetchCompany } from '../api/client'

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

// revenue_est_* stored in thousands USD → format as $XM
const formatRevenue = (v) => (v != null ? `$${(v / 1000).toFixed(1)}M` : null)

function Row({ label, value }) {
  return (
    <div className="flex py-2 border-b border-gray-100 last:border-0">
      <span className="w-44 text-sm text-gray-500 shrink-0">{label}</span>
      <span className="text-sm text-gray-900">{value ?? '—'}</span>
    </div>
  )
}

export default function CompanyModal({ companyId, onClose }) {
  const [company, setCompany] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(false)
    fetchCompany(companyId)
      .then(setCompany)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [companyId])

  // Close on Escape key
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-start justify-between sticky top-0 bg-white">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {loading ? 'Loading...' : (company?.name ?? 'Company')}
            </h2>
            {company && (
              <p className="text-sm text-gray-500 mt-0.5">
                {[company.city, company.state].filter(Boolean).join(', ')}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none ml-4 mt-0.5"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          {loading && (
            <p className="text-gray-400 text-sm py-10 text-center">Loading company details...</p>
          )}

          {error && (
            <p className="text-red-500 text-sm py-10 text-center">Failed to load company.</p>
          )}

          {!loading && !error && company && (
            <>
              {/* Services */}
              <div className="mb-5">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                  Services
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {company.services?.length > 0 ? (
                    company.services.map((svc) => (
                      <span
                        key={svc}
                        className={`px-2.5 py-1 rounded text-xs font-medium ${
                          SERVICE_COLORS[svc] ?? 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {SERVICE_LABELS[svc] ?? svc}
                      </span>
                    ))
                  ) : (
                    <span className="text-sm text-gray-400">None detected</span>
                  )}
                </div>
              </div>

              {/* Company details */}
              <div className="mb-5">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                  Details
                </p>
                <Row label="Ownership Type" value={company.ownership_type} />
                <Row label="Employee Count" value={company.employee_count?.toLocaleString()} />
                <Row label="Revenue (Min)" value={formatRevenue(company.revenue_est_min)} />
                <Row label="Revenue (Max)" value={formatRevenue(company.revenue_est_max)} />
                <Row
                  label="Website"
                  value={
                    company.website ? (
                      <a
                        href={`https://${company.website}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:underline"
                      >
                        {company.website}
                      </a>
                    ) : null
                  }
                />
                <Row
                  label="Thesis Fit Score"
                  value={
                    company.thesis_fit_score != null
                      ? company.thesis_fit_score.toFixed(2)
                      : null
                  }
                />
                <Row label="Data Source" value={company.primary_source} />
                <Row label="Excluded" value={company.is_excluded ? 'Yes' : 'No'} />
              </div>

              {/* Contacts */}
              {company.contacts?.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Contacts ({company.contacts.length})
                  </p>
                  <div className="space-y-2">
                    {company.contacts.map((c) => (
                      <div key={c.id} className="bg-gray-50 rounded-md p-3 text-sm">
                        <p className="font-medium text-gray-900">{c.full_name}</p>
                        {c.title && (
                          <p className="text-gray-500 text-xs mt-0.5">{c.title}</p>
                        )}
                        {c.email && (
                          <p className="text-blue-600 text-xs mt-1">{c.email}</p>
                        )}
                        {c.phone && (
                          <p className="text-gray-500 text-xs">{c.phone}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
