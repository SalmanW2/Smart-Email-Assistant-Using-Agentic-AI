import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor for auth if needed
api.interceptors.request.use((config) => {
  // Add auth headers if available
  return config;
});

export const authAPI = {
  login: (token: string) => api.get(`/auth/login?token=${token}`),
  logout: (userId: string) => api.post('/auth/logout', { user_id: userId }),
};

export const userAPI = {
  getPreferences: (telegramId: number) => api.get(`/user/preferences/${telegramId}`),
  updatePreferences: (telegramId: number, prefs: any) => api.put(`/user/preferences/${telegramId}`, prefs),
  getContacts: (telegramId: number) => api.get(`/user/contacts/${telegramId}`),
};

export const adminAPI = {
  getStats: () => api.get('/admin/stats'),
  getUsers: () => api.get('/admin/users'),
  blockUser: (telegramId: number) => api.post(`/admin/block/${telegramId}`),
  unblockUser: (telegramId: number) => api.delete(`/admin/block/${telegramId}`),
};

export default api;