import pathlib

CLIENT = pathlib.Path("D:/sejong_major/projects/compliance-agent/frontend/src/api/client.js")

CLIENT.write_text(r"""import axios from 'axios';

const api = axios.create({
  baseURL: (import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/api',
  timeout: 15000,
});

api.interceptors.request.use(config => {
  const officerId = localStorage.getItem('officerId') || '1';
  config.headers['X-Officer-Id'] = officerId;
  return config;
});

export const getHealth = () =>
  axios.get((import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/health', { timeout: 3000 }).then(r => r.data);

export const getOfficers = () => api.get('/officers').then(r => r.data);

export const getAlerts = (params) => api.get('/alerts', { params }).then(r => r.data);
export const getAlert = (id) => api.get(`/alerts/${id}`).then(r => r.data);
export const postAlertComment = (id, comment) =>
  api.post(`/alerts/${id}/comments`, { comment }).then(r => r.data);
export const postAlertDisposition = (id, body) =>
  api.post(`/alerts/${id}/disposition`, body).then(r => r.data);

export const getCustomer = (id) => api.get(`/customers/${id}`).then(r => r.data);
export const getCustomerTransactions = (id, params) =>
  api.get(`/customers/${id}/transactions`, { params }).then(r => r.data);
export const getCustomerCases = (id) => api.get(`/customers/${id}/cases`).then(r => r.data);

export const getCase = (id) => api.get(`/cases/${id}`).then(r => r.data);
export const createCase = (body) => api.post('/cases', body).then(r => r.data);
export const linkAlertToCase = (caseId, alertId) =>
  api.post(`/cases/${caseId}/link-alert`, { alert_id: alertId }).then(r => r.data);

export const postTriageRun = (alertId) =>
  api.post('/agent-runs/triage', { alert_id: alertId }, { timeout: 60000 }).then(r => r.data);
export const getAgentRun = (runId) => api.get(`/agent-runs/${runId}`).then(r => r.data);
export const getAgentTrace = (runId) => api.get(`/agent-runs/${runId}/trace`).then(r => r.data);

export const getAuditLog = (params) => api.get('/audit-log', { params }).then(r => r.data);
""", encoding="utf-8")

print("client.js written.")
