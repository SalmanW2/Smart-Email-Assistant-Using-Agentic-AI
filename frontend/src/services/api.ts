import axios from 'axios';

// Automatically points to your local FastAPI during development
// and your Render URL during production.
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:10000/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const authService = {
  login: (telegram_id: number) => {
    window.location.href = `${API_BASE_URL}/auth/login?telegram_id=${telegram_id}`;
  }
};

export const adminService = {
  getStats: (email: string) => api.get(`/admin/stats?email=${email}`),
  getUsers: (email: string) => api.get(`/admin/users?email=${email}`)
};

export const userService = {
  getPreferences: (telegram_id: number) => api.get(`/user/preferences/${telegram_id}`),
  updatePreferences: (data: any) => api.put(`/user/preferences`, data)
};

export default api;