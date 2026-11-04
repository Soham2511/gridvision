/**
 * Types for GridVision Authentication & Identity Access Management.
 */

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  persona: 'RESIDENTIAL' | 'COMMERCIAL' | 'GOVERNMENT';
  role: string;
  meters: string[];
}

export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export interface AuthResponse {
  user: AuthUser;
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number;
}

export interface LoginRequest {
  identifier: string; // username or email
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  confirm_password: string;
}

