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
  status: 'pending' | 'processing' | 'success' | 'failed';
  message: string | null;
  chunks?: number | null;
}

export interface FileImportResponse {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  message: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  current_index: number;
  current_file_tag: string | null;
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
