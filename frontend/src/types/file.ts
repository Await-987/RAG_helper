export type FileType = 'imported' | 'not_imported' | 'ghost';

export interface FileInfo {
  name: string;
  tag: string;
  type: FileType;
  path: string | null;
  chunk_count: number;
}

export interface FileListResponse {
  files: FileInfo[];
  total_files: number;
  total_chunks: number;
  page: number;
  page_size: number;
  total_pages: number;
  stats: {
    imported: number;
    not_imported: number;
    ghost: number;
  };
}

export interface FileUploadResponse {
  success: boolean;
  message: string;
  filename: string;
  path: string;
}

export interface FileImportRequest {
  file_tags: string[];
  dpi?: number;
  debug?: boolean;
}

export interface FileImportStatus {
  file_tag: string;
  status: 'success' | 'failed';
  message: string;
}

export interface FileImportResponse {
  success_count: number;
  failed_count: number;
  total: number;
  results: FileImportStatus[];
}

export interface FileDeleteRequest {
  file_tags: string[];
  delete_local?: boolean;
  delete_images?: boolean;
}

export interface FileDeleteStatus {
  file_tag: string;
  success: boolean;
  message?: string;
}

export interface FileDeleteResponse {
  success_count: number;
  failed_count: number;
  total: number;
  results: FileDeleteStatus[];
}
