import api from './client';
import { getAccessToken } from '@/utils/authToken';
import type {
  FileListResponse,
  FileUploadResponse,
  FileImportRequest,
  FileImportResponse,
  FileDeleteRequest,
  FileDeleteResponse,
} from '@/types';

// Use the same base URL as axios client
const getApiBaseUrl = () => '/api/v1';

export const fileApi = {
  getFiles: async (
    page: number = 1,
    pageSize: number = 20,
    fileType?: string,
    search?: string
  ): Promise<FileListResponse> => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (fileType) {
      params.append('file_type', fileType);
    }
    if (search && search.trim()) {
      params.append('search', search.trim());
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
    const response = await api.post<FileImportResponse>('/files/import', data, {
      timeout: 10 * 60 * 1000,
    });
    return response.data;
  },

  getImportJob: async (jobId: string): Promise<FileImportResponse> => {
    const response = await api.get<FileImportResponse>(`/files/import-jobs/${encodeURIComponent(jobId)}`);
    return response.data;
  },

  getActiveImportJob: async (): Promise<FileImportResponse> => {
    const response = await api.get<FileImportResponse>('/files/import-jobs/active');
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

  getContentUrl: (fileTag: string): string => {
    const params = new URLSearchParams({ file_tag: fileTag });
    return `${getApiBaseUrl()}/files/content?${params.toString()}`;
  },

  fetchContentBlobUrl: async (fileTag: string): Promise<string> => {
    const token = getAccessToken();
    const response = await fetch(fileApi.getContentUrl(fileTag), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch file content: ${response.status}`);
    }

    const blob = await response.blob();
    return URL.createObjectURL(blob);
  },
};
