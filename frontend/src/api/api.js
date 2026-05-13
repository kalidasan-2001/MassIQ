import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8010',
  timeout: 120000,
})

export default api
