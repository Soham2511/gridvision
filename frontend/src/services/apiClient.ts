/**
 * GridVision — Centralized REST API Client
 * Configured via VITE_API_BASE_URL.
 */

export interface ApiResponse<T = unknown> {
  success: boolean;
  data: T;
  meta?: Record<string, unknown>;
  error?: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export class ApiClientError extends Error {
  public code: string;
  public status: number;
  public details?: unknown;

  constructor(message: string, code = 'API_ERROR', status = 500, details?: unknown) {
    super(message);
    this.name = 'ApiClientError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

class ApiClient {
  private baseUrl: string;

  constructor() {
    const rawUrl =
      import.meta.env.VITE_API_BASE_URL ||
      import.meta.env.VITE_API_URL ||
      'http://127.0.0.1:5000/api/v1';

    // Normalize URL (strip trailing slash)
    this.baseUrl = rawUrl.endsWith('/') ? rawUrl.slice(0, -1) : rawUrl;
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
        if (val !== undefined && val !== null && val !== '') {
          url.searchParams.append(key, String(val));
        }
      });
    }

    return url.toString();
  }

  private async request<T>(
    path: string,
    options: RequestInit & { timeoutMs?: number } = {},
    params?: Record<string, string | number | boolean | undefined | null>
  ): Promise<T> {
    const fullUrl = this.buildUrl(path, params);
    const activeHousehold = typeof window !== 'undefined' ? localStorage.getItem('gv_active_entity_household') : null;
    const defaultDevUser = activeHousehold ? activeHousehold.replace(/METER-/i, '') : '2254213';

    const headers: Record<string, string> = {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(defaultDevUser ? { 'X-Dev-User-Id': defaultDevUser } : {}),
      ...((options.headers as Record<string, string>) || {}),
    };

    const timeoutDuration =
      options?.timeoutMs ||
      (path.includes('/assistant/chat') ? 75000 : 30000);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutDuration);

    try {
      const response = await fetch(fullUrl, {
        ...options,
        headers,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      const contentType = response.headers.get('content-type') || '';
      const isJson = contentType.includes('application/json');
      const body: ApiResponse<T> | null = isJson ? await response.json() : null;

      if (!response.ok) {
        const errorMsg =
          body?.error?.message ||
          `Request failed with status ${response.status} (${response.statusText})`;
        const errorCode = body?.error?.code || `HTTP_${response.status}`;
        throw new ApiClientError(errorMsg, errorCode, response.status, body?.error?.details);
      }

      if (body && typeof body === 'object' && 'data' in body) {
        return body.data;
      }

      return body as unknown as T;
    } catch (err) {
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
        throw new ApiClientError(
          `Network connection failed: ${err.message}. Ensure Flask backend is running on ${this.baseUrl}.`,
          'NETWORK_ERROR',
          0
        );
      }
      throw new ApiClientError('An unexpected error occurred during API communication.', 'UNKNOWN', 500);
    }
  }

  public async get<T>(
    path: string,
    params?: Record<string, string | number | boolean | undefined | null>
  ): Promise<T> {
    return this.request<T>(path, { method: 'GET' }, params);
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

  public async postLong<T>(path: string, body?: unknown, timeoutMs = 300000): Promise<T> {
    return this.request<T>(
      path,
      {
        method: 'POST',
        body: body ? JSON.stringify(body) : undefined,
        timeoutMs,
      }
    );
  }

  public async getBlob(path: string): Promise<Blob> {
    const response = await fetch(this.buildUrl(path), {
      headers: { Accept: 'application/octet-stream' },
    });
    if (!response.ok) {
      let message = `Request failed with status ${response.status} (${response.statusText})`;
      try {
        const body = (await response.json()) as ApiResponse<unknown>;
        message = body.error?.message || message;
      } catch {
        // Keep diagnostic
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
}

export const apiClient = new ApiClient();