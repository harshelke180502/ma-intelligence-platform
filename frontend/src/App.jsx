import { useState, useEffect, useCallback } from 'react'
import { fetchKpis } from './api/client'
import KpiCards from './components/KpiCards'
import ServicePieChart from './components/ServicePieChart'
import StateBarChart from './components/StateBarChart'
import CompaniesTable from './components/CompaniesTable'
import CompanyModal from './components/CompanyModal'
import FineTuneCard from './components/FineTuneCard'

export default function App() {
  const [kpis, setKpis] = useState(null)
  const [kpisLoading, setKpisLoading] = useState(true)
  const [selectedCompanyId, setSelectedCompanyId] = useState(null)
  const [tableKey, setTableKey] = useState(0)

  const loadKpis = useCallback(() => {
    setKpisLoading(true)
    fetchKpis()
      .then(setKpis)
      .finally(() => setKpisLoading(false))
  }, [])

  useEffect(() => { loadKpis() }, [loadKpis])

  // Triggered after bulk ownership-revenue fix — refreshes KPI cards + table
  const handleGlobalRefresh = () => {
    loadKpis()
    setTableKey((k) => k + 1)
  }

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
        <KpiCards kpis={kpis} loading={kpisLoading} onRefresh={handleGlobalRefresh} />

        {/* Row 2: Fine-tune model card */}
        <FineTuneCard />

        {/* Row 3: Charts side-by-side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ServicePieChart data={kpis?.by_service} loading={kpisLoading} />
          <StateBarChart data={kpis?.by_state} loading={kpisLoading} />
        </div>

        {/* Row 3: Companies table — key forces remount after bulk revenue fix */}
        <CompaniesTable key={tableKey} onSelectCompany={setSelectedCompanyId} />
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
