import api from './client';
import type {
  FileListResponse,
  FileUploadResponse,
  FileImportRequest,
  FileImportResponse,
  FileDeleteRequest,
  FileDeleteResponse,
} from '@/types';

const API_BASE_URL = '/api/v1';

export const fileApi = {
  getFiles: async (
    page: number = 1,
    pageSize: number = 20,
    fileType?: string
  ): Promise<FileListResponse> => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (fileType) {
      params.append('file_type', fileType);
    }
    const response = await api.get<FileListResponse>(`/files?${params}`);
    return response.data;
  },

  uploadFile: async (file: File): Promise<FileUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post<FileUploadResponse>('/files/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  importFiles: async (data: FileImportRequest): Promise<FileImportResponse> => {
    const response = await api.post<FileImportResponse>('/files/import', data);
    return response.data;
  },

  deleteFiles: async (data: FileDeleteRequest): Promise<FileDeleteResponse> => {
    const response = await api.delete<FileDeleteResponse>('/files', { data });
    return response.data;
  },

  deleteFile: async (
    fileTag: string,
    deleteLocal: boolean = true,
    deleteImages: boolean = true
  ): Promise<FileDeleteResponse> => {
    const params = new URLSearchParams({
      delete_local: String(deleteLocal),
      delete_images: String(deleteImages),
    });
    const response = await api.delete<FileDeleteResponse>(
      `/files/${encodeURIComponent(fileTag)}?${params}`
    );
    return response.data;
  },

  getContentUrl: (fileTag: string): string =>
    `${API_BASE_URL}/files/content/${fileTag
      .split('/')
      .map((segment) => encodeURIComponent(segment))
      .join('/')}`,
};
