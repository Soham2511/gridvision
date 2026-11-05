import React, { createContext, useContext, useEffect, useState } from 'react';
import { AuthResponse, AuthUser, LoginRequest, RegisterRequest } from '../types/auth';
import { authService } from '../services/authService';

export interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (req: LoginRequest) => Promise<AuthResponse>;
  register: (req: RegisterRequest) => Promise<AuthResponse>;
  logout: () => Promise<void>;
  refresh: () => Promise<string>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(() => authService.getStoredUser());
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    let isMounted = true;

    const initializeAuth = async () => {
      const token = authService.getStoredToken();
      if (!token) {
        if (isMounted) {
          setUser(null);
          setIsLoading(false);
        }
        return;
      }

      try {
        const currentUser = await authService.getMe();
        if (isMounted) {
          setUser(currentUser);
        }
      } catch {
        // Try token refresh
        try {
          await authService.refresh();
          const refreshedUser = await authService.getMe();
          if (isMounted) {
            setUser(refreshedUser);
          }
        } catch {
          // Token invalid and refresh failed: clean up
          authService.clearAuthData();
          if (isMounted) {
            setUser(null);
          }
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    initializeAuth();

    return () => {
      isMounted = false;
    };
  }, []);

  const login = async (req: LoginRequest): Promise<AuthResponse> => {
    const res = await authService.login(req);
    setUser(res.user);
    return res;
  };

  const register = async (req: RegisterRequest): Promise<AuthResponse> => {
    const res = await authService.register(req);
    setUser(res.user);
    return res;
  };

  const logout = async (): Promise<void> => {
    await authService.logout();
    setUser(null);
  };

  const refresh = async (): Promise<string> => {
    const newToken = await authService.refresh();
    const refreshedUser = await authService.getMe();
    setUser(refreshedUser);
    return newToken;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
};

