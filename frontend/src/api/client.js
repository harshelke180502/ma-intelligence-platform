import axios from 'axios'

// Requests to /api/* are proxied to http://127.0.0.1:8000 by vite.config.js
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

export const fetchKpis = () =>
  api.get('/kpis').then((r) => r.data)

export const fetchCompanies = (params = {}) =>
  api.get('/companies', { params }).then((r) => r.data)

export const fetchCompany = (id) =>
  api.get(`/companies/${id}`).then((r) => r.data)

export default api
