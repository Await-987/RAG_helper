export interface UserInfo {
  username: string;
  role: 'admin' | 'user';
  created_at?: string;
  last_login?: string;
}

export interface UserCreate {
  username: string;
  password: string;
  role: 'admin' | 'user';
}

export interface UserUpdate {
  role?: 'admin' | 'user';
  password?: string;
}

export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}

export interface ResetPasswordRequest {
  username: string;
  new_password: string;
}

export interface ChangeRoleRequest {
  username: string;
  new_role: 'admin' | 'user';
}
