import { useState, useEffect } from 'react'
import { fetchKpis } from './api/client'
import KpiCards from './components/KpiCards'
import ServicePieChart from './components/ServicePieChart'
import StateBarChart from './components/StateBarChart'
import CompaniesTable from './components/CompaniesTable'
import CompanyModal from './components/CompanyModal'

export default function App() {
  const [kpis, setKpis] = useState(null)
  const [kpisLoading, setKpisLoading] = useState(true)
  const [selectedCompanyId, setSelectedCompanyId] = useState(null)

  useEffect(() => {
    fetchKpis()
      .then(setKpis)
      .finally(() => setKpisLoading(false))
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top nav */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <h1 className="text-xl font-semibold text-gray-900">M&amp;A Intelligence Platform</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Specialty Tax Advisory — Acquisition Pipeline
        </p>
      </header>

      <main className="px-6 py-6 max-w-7xl mx-auto space-y-6">
        {/* Row 1: KPI cards */}
        <KpiCards kpis={kpis} loading={kpisLoading} />

        {/* Row 2: Charts side-by-side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ServicePieChart data={kpis?.by_service} loading={kpisLoading} />
          <StateBarChart data={kpis?.by_state} loading={kpisLoading} />
        </div>

        {/* Row 3: Companies table with filter */}
        <CompaniesTable onSelectCompany={setSelectedCompanyId} />
      </main>

      {/* Company detail modal */}
      {selectedCompanyId && (
        <CompanyModal
          companyId={selectedCompanyId}
          onClose={() => setSelectedCompanyId(null)}
        />
      )}
    </div>
  )
}
