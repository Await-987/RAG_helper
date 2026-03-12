import { useState, useEffect } from 'react';
import { fileApi } from '@/api';
import { useAuthStore } from '@/stores';
import type { FileInfo, FileType } from '@/types';
import {
  Upload,
  FileText,
  Database,
  Trash2,
  RefreshCw,
  Search,
  ChevronLeft,
  ChevronRight,
  Loader2,
  CheckCircle,
  XCircle,
  AlertCircle,
  Download,
  Eye,
} from 'lucide-react';
import clsx from 'clsx';

const PAGE_SIZE = 10;

export function FileManagerPage() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [files, setFiles] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalFiles, setTotalFiles] = useState(0);
  const [totalChunks, setTotalChunks] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);

  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<FileType | 'all'>('all');
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());

  const [uploading, setUploading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [previewFile, setPreviewFile] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Stats
  const [stats, setStats] = useState({
    imported: 0,
    notImported: 0,
    ghost: 0,
  });

  // Fetch files
  const fetchFiles = async () => {
    setLoading(true);
    try {
      const response = await fileApi.getFiles(
        currentPage,
        PAGE_SIZE,
        filterType === 'all' ? undefined : filterType
      );
      setFiles(response.files);
      setTotalFiles(response.total_files);
      setTotalChunks(response.total_chunks);
      setTotalPages(response.total_pages);
      setStats({
        imported: response.stats.imported,
        notImported: response.stats.not_imported,
        ghost: response.stats.ghost,
      });
    } catch (error) {
      console.error('Failed to fetch files:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
    setSelectedFiles(new Set());
  }, [currentPage, filterType]);

  useEffect(() => {
    if (!previewFile) {
      setPreviewUrl(null);
      setPreviewLoading(false);
      setPreviewError(null);
      return;
    }

    let cancelled = false;
    let objectUrl = '';

    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewUrl(null);

    const loadPreview = async () => {
      try {
        objectUrl = await fileApi.fetchContentBlobUrl(previewFile);
        if (!cancelled) {
          setPreviewUrl(objectUrl);
        }
      } catch (error) {
        console.error('Failed to load preview:', error);
        if (!cancelled) {
          setPreviewError('预览加载失败，请重新登录后重试');
        }
      } finally {
        if (!cancelled) {
          setPreviewLoading(false);
        }
      }
    };

    loadPreview();

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [previewFile]);

  // Filter by search query
  const filteredFiles = searchQuery
    ? files.filter((f) => f.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : files;

  // Handle file upload
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;

    setUploading(true);
    try {
      for (const file of Array.from(fileList)) {
        await fileApi.uploadFile(file);
      }
      await fetchFiles();
    } catch (error) {
      console.error('Upload failed:', error);
      alert('上传失败');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  // Handle file import
  const handleImport = async () => {
    const filesToImport = files
      .filter((f) => selectedFiles.has(f.tag) && f.type === 'not_imported')
      .map((f) => f.tag);

    if (filesToImport.length === 0) {
      alert('请选择要导入的未建库文件');
      return;
    }

    if (!confirm(`确定要导入 ${filesToImport.length} 个文件吗？`)) return;

    setImporting(true);
    try {
      const result = await fileApi.importFiles({ file_tags: filesToImport });
      alert(
        `导入完成：成功 ${result.success_count} 个，失败 ${result.failed_count} 个`
      );
      await fetchFiles();
      setSelectedFiles(new Set());
    } catch (error) {
      console.error('Import failed:', error);
      alert('导入失败');
    } finally {
      setImporting(false);
    }
  };

  // Handle file delete
  const handleDelete = async (fileTag: string) => {
    if (!confirm('确定要删除此文件吗？')) return;

    setDeleting(true);
    try {
      await fileApi.deleteFile(fileTag);
      await fetchFiles();
    } catch (error) {
      console.error('Delete failed:', error);
      alert('删除失败');
    } finally {
      setDeleting(false);
    }
  };

  // Handle batch delete
  const handleBatchDelete = async () => {
    const filesToDelete = Array.from(selectedFiles);
    if (filesToDelete.length === 0) {
      alert('请选择要删除的文件');
      return;
    }

    if (!confirm(`确定要删除 ${filesToDelete.length} 个文件吗？`)) return;

    setDeleting(true);
    try {
      await fileApi.deleteFiles({ file_tags: filesToDelete });
      await fetchFiles();
      setSelectedFiles(new Set());
    } catch (error) {
      console.error('Batch delete failed:', error);
      alert('批量删除失败');
    } finally {
      setDeleting(false);
    }
  };

  // Toggle file selection
  const toggleSelection = (tag: string) => {
    const newSelected = new Set(selectedFiles);
    if (newSelected.has(tag)) {
      newSelected.delete(tag);
    } else {
      newSelected.add(tag);
    }
    setSelectedFiles(newSelected);
  };

  // Select all on current page
  const toggleSelectAll = () => {
    if (selectedFiles.size === filteredFiles.length) {
      setSelectedFiles(new Set());
    } else {
      setSelectedFiles(new Set(filteredFiles.map((f) => f.tag)));
    }
  };

  // Get type badge
  const getTypeBadge = (type: FileType) => {
    switch (type) {
      case 'imported':
        return (
          <span className="flex items-center gap-1 text-green-400 text-sm">
            <CheckCircle size={14} />
            已建库
          </span>
        );
      case 'not_imported':
        return (
          <span className="flex items-center gap-1 text-orange-400 text-sm">
            <AlertCircle size={14} />
            未建库
          </span>
        );
      case 'ghost':
        return (
          <span className="flex items-center gap-1 text-red-400 text-sm">
            <XCircle size={14} />
            残留数据
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-dark-border bg-dark-card">
        <h1 className="text-xl font-bold text-white">文件管理</h1>
      </div>

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <div className="card text-center">
            <p className="text-2xl font-bold text-white">
              {stats.imported + stats.notImported}
            </p>
            <p className="text-sm text-gray-400">本地文件</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-green-400">{stats.imported}</p>
            <p className="text-sm text-gray-400">已建库</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-orange-400">{stats.notImported}</p>
            <p className="text-sm text-gray-400">未建库</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-red-400">{stats.ghost}</p>
            <p className="text-sm text-gray-400">残留数据</p>
          </div>
        </div>

        {/* Toolbar */}
        <div className="flex flex-wrap gap-3 mb-4">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索文件..."
              className="input-field pl-10"
            />
          </div>

          {/* Filter */}
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value as FileType | 'all')}
            className="input-field w-auto"
          >
            <option value="all">全部类型</option>
            <option value="imported">已建库</option>
            <option value="not_imported">未建库</option>
            <option value="ghost">残留数据</option>
          </select>

          {/* Refresh */}
          <button
            onClick={() => fetchFiles()}
            disabled={loading}
            className="btn btn-secondary"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>

          {/* Admin actions */}
          {isAdmin && (
            <>
              {/* Upload */}
              <label className="btn btn-primary cursor-pointer flex items-center gap-2">
                <Upload size={18} />
                <span>上传</span>
                <input
                  type="file"
                  accept=".pdf,.doc,.docx,.txt,.md"
                  multiple
                  onChange={handleUpload}
                  className="hidden"
                  disabled={uploading}
                />
              </label>

              {/* Import */}
              <button
                onClick={handleImport}
                disabled={importing || selectedFiles.size === 0}
                className="btn btn-primary flex items-center gap-2"
              >
                {importing ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <Database size={18} />
                )}
                <span>导入选中</span>
              </button>

              {/* Delete */}
              <button
                onClick={handleBatchDelete}
                disabled={deleting || selectedFiles.size === 0}
                className="btn btn-danger flex items-center gap-2"
              >
                <Trash2 size={18} />
                <span>删除选中</span>
              </button>
            </>
          )}
        </div>

        {/* File list */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={24} className="animate-spin text-primary-400" />
          </div>
        ) : filteredFiles.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <FileText size={48} className="mx-auto mb-4 opacity-50" />
            <p>没有找到文件</p>
          </div>
        ) : (
          <>
            {/* Select all (admin only) */}
            {isAdmin && (
              <div className="flex items-center gap-2 mb-3 px-2">
                <input
                  type="checkbox"
                  checked={selectedFiles.size === filteredFiles.length}
                  onChange={toggleSelectAll}
                  className="w-4 h-4 rounded border-gray-600 bg-dark-bg"
                />
                <span className="text-sm text-gray-400">
                  全选当前页 ({selectedFiles.size} 已选)
                </span>
              </div>
            )}

            {/* File table */}
            <div className="space-y-2">
              {filteredFiles.map((file) => (
                <div
                  key={file.tag}
                  className={clsx(
                    'card flex items-center gap-4',
                    selectedFiles.has(file.tag) && 'ring-2 ring-primary-500'
                  )}
                >
                  {/* Checkbox (admin only) */}
                  {isAdmin && (
                    <input
                      type="checkbox"
                      checked={selectedFiles.has(file.tag)}
                      onChange={() => toggleSelection(file.tag)}
                      className="w-4 h-4 rounded border-gray-600 bg-dark-bg"
                    />
                  )}

                  {/* Icon */}
                  <div className="w-10 h-10 rounded-lg bg-dark-hover flex items-center justify-center flex-shrink-0">
                    {file.type === 'ghost' ? (
                      <span className="text-lg">👻</span>
                    ) : (
                      <FileText size={20} className="text-gray-400" />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-gray-100 truncate">{file.name}</p>
                    <div className="flex items-center gap-3 text-sm text-gray-400">
                      <span>{file.chunk_count} 个切片</span>
                      {getTypeBadge(file.type)}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {file.path && file.name.toLowerCase().endsWith('.pdf') && (
                      <button
                        onClick={() => setPreviewFile(file.tag)}
                        className="p-2 text-gray-400 hover:text-gray-100 hover:bg-dark-hover rounded-lg transition-colors"
                        title="预览"
                      >
                        <Eye size={18} />
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        onClick={() => handleDelete(file.tag)}
                        disabled={deleting}
                        className="p-2 text-gray-400 hover:text-red-400 hover:bg-dark-hover rounded-lg transition-colors"
                        title="删除"
                      >
                        <Trash2 size={18} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-center gap-4 mt-6">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="btn btn-secondary"
              >
                <ChevronLeft size={18} />
              </button>
              <span className="text-gray-400">
                第 {currentPage} / {totalPages} 页
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="btn btn-secondary"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </>
        )}
      </div>

      {/* PDF Preview Modal */}
      {previewFile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="w-full max-w-4xl h-[90vh] bg-dark-card rounded-xl overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-dark-border">
              <h3 className="font-medium text-white truncate">
                {previewFile.split('/').pop()}
              </h3>
              <button
                onClick={() => setPreviewFile(null)}
                className="p-2 text-gray-400 hover:text-white hover:bg-dark-hover rounded-lg"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 p-4">
              {previewLoading ? (
                <div className="w-full h-full rounded-lg border border-dark-border bg-dark-surface flex items-center justify-center text-gray-400 gap-3">
                  <Loader2 size={18} className="animate-spin" />
                  <span>正在加载预览...</span>
                </div>
              ) : previewError ? (
                <div className="w-full h-full rounded-lg border border-red-500/30 bg-red-500/10 flex items-center justify-center text-red-300">
                  {previewError}
                </div>
              ) : previewUrl ? (
                <iframe
                  src={previewUrl}
                  className="w-full h-full rounded-lg"
                  title="PDF Preview"
                />
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
