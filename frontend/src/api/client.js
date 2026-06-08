import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
});

export const getCustomers = (params) => api.get('/customers', { params }).then(r => r.data);
export const getCustomer = (id) => api.get(`/customers/${id}`).then(r => r.data);
export const getCustomerAlerts = (id) => api.get(`/customers/${id}/alerts`).then(r => r.data);
export const getCustomerTransactions = (id) => api.get(`/customers/${id}/transactions`).then(r => r.data);

export const getAlerts = (params) => api.get('/alerts', { params }).then(r => r.data);
export const getAlert = (id) => api.get(`/alerts/${id}`).then(r => r.data);
export const updateAlertStatus = (id, status) => api.patch(`/alerts/${id}/status`, { status }).then(r => r.data);

export const getCases = (params) => api.get('/cases', { params }).then(r => r.data);
export const getCase = (id) => api.get(`/cases/${id}`).then(r => r.data);

export const getHealth = () => axios.get(`${API_BASE_URL}/health`, { timeout: 3000 }).then(r => r.data);
