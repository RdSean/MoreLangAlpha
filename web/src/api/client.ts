/** Shared REST client for first-party cookie-authenticated API calls. */
import axios, { type AxiosError } from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '';

export const api = axios.create({
  baseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError & { status?: number; rateLimitInfo?: Record<string, unknown>; retryAfter?: number | null }) => {
    if (error.response?.status === 429) {
      const detail = (error.response.data as Record<string, unknown>)?.detail || {};
      error.status = 429;
      error.rateLimitInfo = typeof detail === 'object' ? detail as Record<string, unknown> : {};
      error.retryAfter = parseInt(error.response.headers?.['retry-after'] as string, 10) || null;
    }
    return Promise.reject(error);
  },
);
