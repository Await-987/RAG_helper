import axios from 'axios';
import { clearAccessToken, getAccessToken } from '@/utils/authToken';

const API_BASE_URL = '/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10 * 60 * 1000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: add token
api.interceptors.request.use(
  (config) => {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor: handle errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearAccessToken();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
