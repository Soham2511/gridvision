/**
 * Centralized Authentication Service for GridVision.
 */

import { apiClient } from './apiClient';
import {
  AuthResponse,
  AuthUser,
  LoginRequest,
  RegisterRequest,
} from '../types/auth';

const ACCESS_TOKEN_KEY = 'gv_access_token';
const USER_KEY = 'gv_user';

export const authService = {
  getStoredToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },

  getStoredUser(): AuthUser | null {
    if (typeof window === 'undefined') return null;
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },

  setAuthData(data: AuthResponse): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    if (data.user.meters && data.user.meters.length > 0) {
      localStorage.setItem('gv_active_entity_household', data.user.meters[0]);
    }
  },

  clearAuthData(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },

  async register(req: RegisterRequest): Promise<AuthResponse> {
    const res = await apiClient.post<AuthResponse>('/auth/register', req);
    this.setAuthData(res);
    return res;
  },

  async login(req: LoginRequest): Promise<AuthResponse> {
    const res = await apiClient.post<AuthResponse>('/auth/login', req);
    this.setAuthData(res);
    return res;
  },

  async logout(): Promise<void> {
    try {
      await apiClient.post('/auth/logout', {});
    } catch {
      // Ignore network errors on logout
    } finally {
      this.clearAuthData();
    }
  },

  async refresh(): Promise<string> {
    const res = await apiClient.post<{ access_token: string }>('/auth/refresh', {});
    if (res?.access_token) {
      localStorage.setItem(ACCESS_TOKEN_KEY, res.access_token);
      return res.access_token;
    }
    throw new Error('Refresh failed: No access token returned');
  },

  async getMe(): Promise<AuthUser> {
    const res = await apiClient.get<AuthUser>('/auth/me');
    if (res) {
      localStorage.setItem(USER_KEY, JSON.stringify(res));
    }
    return res;
  },
};

