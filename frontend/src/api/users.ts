import api from './client';
import type {
  UserInfo,
  UserCreate,
  ChangePasswordRequest,
  ResetPasswordRequest,
  ChangeRoleRequest,
} from '@/types';

export const userApi = {
  getUsers: async (): Promise<UserInfo[]> => {
    const response = await api.get<{ users: UserInfo[]; total: number }>('/users');
    return response.data.users;
  },

  createUser: async (data: UserCreate): Promise<UserInfo> => {
    const response = await api.post<UserInfo>('/users', data);
    return response.data;
  },

  getUser: async (username: string): Promise<UserInfo> => {
    const response = await api.get<UserInfo>(`/users/${username}`);
    return response.data;
  },

  deleteUser: async (username: string): Promise<void> => {
    await api.delete(`/users/${username}`);
  },

  changePassword: async (data: ChangePasswordRequest): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>('/users/change-password', data);
    return response.data;
  },

  resetPassword: async (data: ResetPasswordRequest): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>('/users/reset-password', data);
    return response.data;
  },

  changeRole: async (data: ChangeRoleRequest): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>('/users/change-role', data);
    return response.data;
  },
};
