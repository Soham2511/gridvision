/**
 * Centralized API Client for GridVision frontend.
 * Provides unified fetch wrapper with error handling, timeouts, and auth.
 */

export interface ApiResponse<T = unknown> {
  status: 'success' | 'error';
  data: T;
  error?: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface ApiCredentials {
  username: string;
  password: string;
}

export class ApiClientError extends Error {
  public code: string;
  public status: number;
  public details?: unknown;
  public requestId?: string;

  constructor(
    message: string,
    code = 'API_ERROR',
    status = 500,
    details?: unknown,
    requestId?: string,
  ) {
    super(message);
    this.name = 'ApiClientError';
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
  }
}

class ApiClient {
  private baseUrl: string;

  constructor() {
    this.baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '');
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  private buildUrl(path: string, params?: Record<string, string | number | boolean | undefined | null>): string {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const fullPath = `${this.baseUrl}${cleanPath}`;
    const base =
      typeof window !== 'undefined' && window.location?.origin
        ? window.location.origin
        : 'http://127.0.0.1:5000';
    const url = new URL(fullPath, base);

    if (params) {
      Object.entries(params).forEach(([key, val]) => {
        if (val !== undefined && val !== null) {
          url.searchParams.append(key, String(val));
        }
      });
    }

    return url.toString();
  }

  private async request<T>(
    path: string,
    options: RequestInit & { timeoutMs?: number } = {},
    params?: Record<string, string | number | boolean | undefined | null>,
    timeoutMs?: number,
    credentials?: ApiCredentials,
  ): Promise<T> {
    const fullUrl = this.buildUrl(path, params);
    const activePersona = typeof window !== 'undefined' ? localStorage.getItem('gv_current_persona') : null;
    const activeEntity = typeof window !== 'undefined'
      ? (
          (activePersona ? localStorage.getItem(`gv_active_entity_${activePersona}`) : null) ||
          localStorage.getItem('gv_active_entity_residential') ||
          localStorage.getItem('gv_active_entity_commercial') ||
          localStorage.getItem('gv_active_entity_household')
        )
      : null;
    const defaultDevUser = activeEntity ? activeEntity.replace(/^METER-/i, '') : '2254213';
    const accessToken = typeof window !== 'undefined' ? localStorage.getItem('gv_access_token') : null;

    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(defaultDevUser ? { 'X-Dev-User-Id': defaultDevUser } : {}),
      ...(activePersona ? { 'X-Persona': activePersona } : {}),
      ...((options.headers as Record<string, string>) || {}),
    };
    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    if (credentials) {
      const encoded = new TextEncoder().encode(
        `${credentials.username}:${credentials.password}`,
      );
      const binary = Array.from(encoded, (byte) => String.fromCharCode(byte)).join('');
      headers.Authorization = `Basic ${btoa(binary)}`;
    }

    const timeoutDuration =
      timeoutMs ||
      options?.timeoutMs ||
      (path.includes('/assistant/chat') ? 75000 : 30000);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutDuration);

    try {
      const response = await fetch(fullUrl, {
        credentials: 'include',
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      let body: { error?: { message?: string; code?: string; details?: unknown } } | null = null;
      try {
        body = await response.json();
      } catch {
        // Response might not be JSON (e.g. 204 or plain text)
      }

      if (!response.ok) {
        const errorMsg =
          body?.error?.message ||
          `Request failed with status ${response.status} (${response.statusText})`;
        const errorCode = body?.error?.code || `HTTP_${response.status}`;
        throw new ApiClientError(
          errorMsg,
          errorCode,
          response.status,
          body?.error?.details,
          response.headers.get('X-Request-ID') || undefined,
        );
      }

      if (body && typeof body === 'object' && 'data' in body) {
        return body.data as T;
      }

      return body as T;
    } catch (err: unknown) {
      clearTimeout(timeoutId);
      if (err instanceof ApiClientError) {
        throw err;
      }
      if (err instanceof Error) {
        if (err.name === 'AbortError') {
          const secs = Math.round(timeoutDuration / 1000);
          throw new ApiClientError(
            `Request to ${path} timed out after ${secs}s. Ensure backend is running.`,
            'TIMEOUT_ERROR',
            408
          );
        }
        throw new ApiClientError(err.message, 'NETWORK_ERROR', 0);
      }
      throw new ApiClientError('An unknown error occurred.', 'UNKNOWN_ERROR', 500);
    }
  }

  public async get<T>(
    path: string,
    params?: Record<string, string | number | boolean | undefined | null>,
    options?: RequestInit & { timeoutMs?: number }
  ): Promise<T> {
    return this.request<T>(path, { method: 'GET', ...options }, params);
  }

  public async post<T>(
    path: string,
    body?: unknown,
    params?: Record<string, string | number | boolean | undefined | null>,
    options?: RequestInit & { timeoutMs?: number }
  ): Promise<T> {
    return this.request<T>(
      path,
      {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
        ...options,
      },
      params
    );
  }

  public async postLong<T>(
    path: string,
    body?: unknown,
    timeoutMs = 60000,
  ): Promise<T> {
    return this.request<T>(
      path,
      {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
      },
      undefined,
      timeoutMs,
    );
  }

  public async postAuthenticated<T>(
    path: string,
    body: unknown,
    credentials: ApiCredentials,
    timeoutMs = 15000,
  ): Promise<T> {
    return this.request<T>(
      path,
      { method: 'POST', body: JSON.stringify(body) },
      undefined,
      timeoutMs,
      credentials,
    );
  }

  public async postLongAuthenticated<T>(
    path: string,
    body: unknown,
    credentials: ApiCredentials,
    timeoutMs = 300000,
  ): Promise<T> {
    return this.request<T>(
      path,
      { method: 'POST', body: JSON.stringify(body) },
      undefined,
      timeoutMs,
      credentials,
    );
  }

  public async getAuthenticated<T>(
    path: string,
    credentials: ApiCredentials,
  ): Promise<T> {
    return this.request<T>(
      path,
      { method: 'GET' },
      undefined,
      15000,
      credentials,
    );
  }

  public async uploadAuthenticated<T>(
    path: string,
    file: File,
    credentials: ApiCredentials,
  ): Promise<T> {
    const formData = new FormData();
    formData.append('file', file);
    return this.request<T>(
      path,
      { method: 'POST', body: formData },
      undefined,
      300000,
      credentials,
    );
  }

  public async getBlob(
    path: string,
    params?: Record<string, string | number | boolean | undefined | null>,
    credentials?: ApiCredentials,
  ): Promise<Blob> {
    const fullUrl = this.buildUrl(path, params);
    const headers: Record<string, string> = {};
    if (credentials) {
      const encoded = new TextEncoder().encode(
        `${credentials.username}:${credentials.password}`,
      );
      const binary = Array.from(encoded, (byte) => String.fromCharCode(byte)).join('');
      headers.Authorization = `Basic ${btoa(binary)}`;
    }
    const response = await fetch(fullUrl, {
      method: 'GET',
      headers,
      credentials: 'include',
    });
    if (!response.ok) {
      let message = `Request failed with status ${response.status} (${response.statusText})`;
      try {
        const body = (await response.json()) as ApiResponse<unknown>;
        message = body.error?.message || message;
      } catch {
        // Keep the HTTP diagnostic when the error body is not JSON.
      }
      throw new ApiClientError(message, `HTTP_${response.status}`, response.status);
    }
    return response.blob();
  }

  public async put<T>(
    path: string,
    body?: unknown,
    params?: Record<string, string | number | boolean | undefined | null>
  ): Promise<T> {
    return this.request<T>(
      path,
      {
        method: 'PUT',
        body: body ? JSON.stringify(body) : undefined,
      },
      params
    );
  }

  public async patch<T>(
    path: string,
    body?: unknown,
    params?: Record<string, string | number | boolean | undefined | null>
  ): Promise<T> {
    return this.request<T>(
      path,
      {
        method: 'PATCH',
        body: body ? JSON.stringify(body) : undefined,
      },
      params
    );
  }

  public async delete<T>(
    path: string,
    params?: Record<string, string | number | boolean | undefined | null>
  ): Promise<T> {
    return this.request<T>(path, { method: 'DELETE' }, params);
  }
}

export const apiClient = new ApiClient();
