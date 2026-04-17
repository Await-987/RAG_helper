export interface User {
  username: string;
  role: 'admin' | 'user';
  created_at?: string;
  last_login?: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}
