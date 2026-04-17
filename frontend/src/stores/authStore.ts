import { create } from 'zustand';
import type { User, AuthState, LoginRequest } from '@/types';
import { authApi } from '@/api';
import { clearAccessToken, getAccessToken, setAccessToken } from '@/utils/authToken';

interface AuthStore extends AuthState {
  login: (data: LoginRequest) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
  setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,

  login: async (data: LoginRequest) => {
    set({ isLoading: true });
    try {
      const response = await authApi.login(data);
      setAccessToken(response.access_token);
      const user = await authApi.getCurrentUser();
      set({
        user,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (error) {
      clearAccessToken();
      set({ isLoading: false, user: null, isAuthenticated: false });
      throw error;
    }
  },

  logout: () => {
    clearAccessToken();
    set({
      user: null,
      isAuthenticated: false,
    });
  },

  checkAuth: async () => {
    const token = getAccessToken();
    set({ isLoading: true });

    if (!token) {
      set({ isAuthenticated: false, user: null, isLoading: false });
      return;
    }

    try {
      const user = await authApi.getCurrentUser();
      set({
        user,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch {
      clearAccessToken();
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  setUser: (user) => {
    set({ user });
  },
}));
