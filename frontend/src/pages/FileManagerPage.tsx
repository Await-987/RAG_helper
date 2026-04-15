import { useState, useEffect, useCallback, useDeferredValue } from 'react';
import { fileApi } from '@/api/files';
import type { FileInfo, FileType, FileImportResponse } from '@/types/file';
import { useAuthStore } from '@/stores/authStore';
import {
  Upload,
  Trash2,
  Search,
  FileText,
  RefreshCw,
  Loader2,
  Eye,
  X,
  ChevronLeft,
  ChevronRight,
  CheckCircle,
  XCircle,
  AlertCircle,
  Database,
} from 'lucide-react';

const PAGE_SIZE = 10;

const STATUS_CONFIG: Record<FileType, { label: string; color: string; icon: React.ReactNode }> = {
  imported: {
    label: '已建库',
    color: 'bg-green-600/20 text-green-400 border-green-600/30',
    icon: <CheckCircle size={12} />,
  },
  not_imported: {
    label: '未建库',
    color: 'bg-yellow-600/20 text-yellow-400 border-yellow-600/30',
    icon: <AlertCircle size={12} />,
  },
  ghost: {
    label: '残留',
    color: 'bg-red-600/20 text-red-400 border-red-600/30',
    icon: <XCircle size={12} />,
  },
};

export function FileManagerPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  // Pagination & data
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [totalPages, setTotalPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  const [stats, setStats] = useState({ imported: 0, not_imported: 0, ghost: 0 });
  const [loading, setLoading] = useState(true);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const deferredSearch = useDeferredValue(searchQuery.trim());
  const [filterType, setFilterType] = useState<string>('');

  // Selection: tag → type mapping (works across pages)
  const [selected, setSelected] = useState<Record<string, FileType>>({});

  const selectedCount = Object.keys(selected).length;
  const importableTags = Object.entries(selected)
    .filter(([, t]) => t === 'not_imported')
    .map(([tag]) => tag);
  const importableCount = importableTags.length;

  // Actions
  const [uploading, setUploading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importJob, setImportJob] = useState<FileImportResponse | null>(null);
  const [loadingAll, setLoadingAll] = useState(false);

  // Preview
  const [previewFile, setPreviewFile] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // ---- Fetch files ----
  const fetchFiles = useCallback(
    async (page = currentPage, type = filterType, search = deferredSearch) => {
      setLoading(true);
      try {
        const res = await fileApi.getFiles(page, PAGE_SIZE, type || undefined, search || undefined);
        setFiles(res.files);
        setTotalPages(res.total_pages);
        setStats(res.stats);
      } catch (err) {
        console.error('Failed to load files:', err);
      } finally {
        setLoading(false);
      }
    },
    [currentPage, filterType, deferredSearch]
  );

  // Re-fetch when page / filter / debounced search change
  useEffect(() => {
    fetchFiles(currentPage, filterType, deferredSearch);
    setSelected({});
  }, [currentPage, filterType, deferredSearch]);

  // ---- Active import job on mount ----
  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    fileApi.getActiveImportJob().then((job) => {
      if (!cancelled && ['queued', 'running'].includes(job.status)) {
        setImportJob(job);
      }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [isAdmin]);

  // ---- Poll import job ----
  useEffect(() => {
    if (!importJob || !['queued', 'running'].includes(importJob.status)) return;
    let cancelled = false;
    const interval = window.setInterval(async () => {
      try {
        const next = await fileApi.getImportJob(importJob.job_id);
        if (cancelled) return;
        setImportJob(next);
        if (!['queued', 'running'].includes(next.status)) {
          clearInterval(interval);
          setImporting(false);
          setCurrentPage(1);
          setSelected({});
          await fetchFiles(1, filterType, deferredSearch);
        }
      } catch {
        clearInterval(interval);
        setImporting(false);
      }
    }, 2000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [importJob?.job_id, importJob?.status]);

  // ---- Preview lifecycle ----
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

    fileApi.fetchContentBlobUrl(previewFile).then((url) => {
      objectUrl = url;
      if (!cancelled) setPreviewUrl(url);
    }).catch(() => {
      if (!cancelled) setPreviewError('预览加载失败');
    }).finally(() => {
      if (!cancelled) setPreviewLoading(false);
    });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [previewFile]);

  // ---- Handlers ----
  const handleUpload = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = '.pdf,.doc,.docx,.txt,.md';
    input.onchange = async (e) => {
      const fileList = (e.target as HTMLInputElement).files;
      if (!fileList) return;
      setUploading(true);
      try {
        for (const file of Array.from(fileList)) {
          await fileApi.uploadFile(file);
        }
        setCurrentPage(1);
        setFilterType('not_imported');
        await fetchFiles(1, 'not_imported', deferredSearch);
      } catch (err) {
        console.error('Upload failed:', err);
      } finally {
        setUploading(false);
      }
    };
    input.click();
  }, [fetchFiles, deferredSearch]);

  const handleImport = useCallback(async () => {
    if (importableCount === 0) { alert('请选择要导入的未建库文件'); return; }
    if (!confirm(`确定导入 ${importableCount} 个文件？`)) return;

    setImporting(true);
    try {
      const job = await fileApi.importFiles({ file_tags: importableTags });
      setImportJob(job);
      setSelected({});
    } catch (err) {
      console.error('Import failed:', err);
      setImporting(false);
    }
  }, [importableCount, importableTags]);

  const handleDelete = useCallback(async (tag: string) => {
    if (!confirm('确定删除此文件？')) return;
    try {
      await fileApi.deleteFile(tag);
      await fetchFiles();
    } catch (err) {
      console.error('Delete failed:', err);
    }
  }, [fetchFiles]);

  const handleBatchDelete = useCallback(async () => {
    const tags = Object.keys(selected);
    if (tags.length === 0) return;
    if (!confirm(`确定删除 ${tags.length} 个文件？`)) return;
    try {
      await fileApi.deleteFiles({ file_tags: tags });
      setSelected({});
      await fetchFiles();
    } catch (err) {
      console.error('Batch delete failed:', err);
    }
  }, [selected, fetchFiles]);

  const toggleFile = useCallback((tag: string, type: FileType) => {
    setSelected((prev) => {
      const next = { ...prev };
      if (tag in next) delete next[tag];
      else next[tag] = type;
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelected((prev) => {
      const currentPageTags = files.map((f) => f.tag);
      const allCurrentSelected = currentPageTags.every((t) => t in prev);
      if (allCurrentSelected) {
        const next = { ...prev };
        currentPageTags.forEach((t) => delete next[t]);
        return next;
      }
      const next = { ...prev };
      files.forEach((f) => { next[f.tag] = f.type; });
      return next;
    });
  }, [files]);

  const selectAllPages = useCallback(async () => {
    setLoadingAll(true);
    try {
      const all: Record<string, FileType> = {};
      let page = 1;
      for (;;) {
        const res = await fileApi.getFiles(page, 100, filterType || undefined, deferredSearch || undefined);
        res.files.forEach((f) => { all[f.tag] = f.type; });
        if (page >= res.total_pages) break;
        page++;
      }
      setSelected(all);
    } catch (err) {
      console.error('Failed to select all:', err);
    } finally {
      setLoadingAll(false);
    }
  }, [filterType, deferredSearch]);

  const clearSelection = useCallback(() => setSelected({}), []);

  const isPdf = (f: FileInfo) => f.path && f.name.toLowerCase().endsWith('.pdf');
  const currentPageAllSelected = files.length > 0 && files.every((f) => f.tag in selected);

  return (
    <div className="h-full overflow-y-auto custom-scrollbar p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-xl font-bold text-white mb-6">文件管理</h1>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="card text-center">
            <div className="text-2xl font-bold text-white">{stats.imported + stats.not_imported}</div>
            <div className="text-sm text-gray-400">本地文件</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-bold text-green-400">{stats.imported}</div>
            <div className="text-sm text-gray-400">已建库</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-bold text-yellow-400">{stats.not_imported}</div>
            <div className="text-sm text-gray-400">未建库</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-bold text-red-400">{stats.ghost}</div>
            <div className="text-sm text-gray-400">残留数据</div>
          </div>
        </div>

        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          {isAdmin && (
            <>
              <button onClick={handleUpload} disabled={uploading} className="btn btn-primary flex items-center gap-2">
                {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                上传
              </button>
              <button
                onClick={handleImport}
                disabled={importing || importableCount === 0 || (!!importJob && ['queued', 'running'].includes(importJob.status))}
                className="btn btn-secondary flex items-center gap-2"
              >
                {importing ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
                导入选中 ({importableCount})
              </button>
              {selectedCount > 0 && (
                <button onClick={handleBatchDelete} className="btn btn-secondary flex items-center gap-2 text-red-400 hover:text-red-300">
                  <Trash2 size={14} />
                  删除选中 ({selectedCount})
                </button>
              )}
            </>
          )}
          <div className="flex-1" />
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              placeholder="搜索文件..."
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
              className="bg-dark-card border border-dark-border rounded-lg pl-9 pr-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-primary-500 w-48"
            />
          </div>
          <select
            value={filterType}
            onChange={(e) => { setFilterType(e.target.value); setCurrentPage(1); }}
            className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-primary-500"
          >
            <option value="">全部</option>
            <option value="imported">已建库</option>
            <option value="not_imported">未建库</option>
            <option value="ghost">残留</option>
          </select>
          <button onClick={() => fetchFiles()} className="p-2 rounded-lg hover:bg-dark-hover text-gray-400">
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>

        {/* Import job progress */}
        {importJob && ['queued', 'running'].includes(importJob.status) && (
          <div className="mb-4 rounded-xl border border-primary-500/30 bg-primary-500/10 px-4 py-3 text-sm text-gray-200">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium text-white">
                  索引任务：{importJob.status === 'queued' ? '排队中' : '执行中'}
                </p>
                <p className="text-gray-300">
                  成功 {importJob.success_count} / 失败 {importJob.failed_count} / 总计 {importJob.total}
                </p>
              </div>
              <div className="text-right text-gray-300">
                <p>进度 {Math.min(importJob.current_index, importJob.total)} / {importJob.total}</p>
                <p className="truncate max-w-[320px] text-xs">{importJob.current_file_tag || '等待执行'}</p>
              </div>
            </div>
          </div>
        )}

        {/* File list */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={24} className="animate-spin text-primary-400" />
          </div>
        ) : files.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <FileText size={40} className="mx-auto mb-3 opacity-40" />
            <p>{deferredSearch ? '没有匹配的文件' : '暂无文件'}</p>
          </div>
        ) : (
          <>
            {/* Select all row */}
            {isAdmin && (
              <div className="flex items-center gap-3 mb-2 px-1">
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={currentPageAllSelected}
                    onChange={toggleSelectAll}
                    className="rounded border-gray-600"
                  />
                  <span className="text-xs text-gray-400">全选当前页</span>
                </label>
                {selectedCount <= files.length && (
                  <button
                    onClick={selectAllPages}
                    disabled={loadingAll}
                    className="text-xs text-primary-400 hover:text-primary-300 disabled:opacity-40"
                  >
                    {loadingAll ? '加载中...' : totalPages > 1 ? `选择所有页 (${totalPages}页)` : '全选'}
                  </button>
                )}
                {selectedCount > 0 && (
                  <button onClick={clearSelection} className="text-xs text-gray-500 hover:text-gray-300">
                    清除选择 ({selectedCount})
                  </button>
                )}
              </div>
            )}

            <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
              <table className="w-full table-fixed">
                <thead>
                  <tr className="border-b border-dark-border">
                    {isAdmin && <th className="w-10 px-3 py-3" />}
                    <th className="text-left px-4 py-3 text-sm text-gray-400 font-medium" />
                    <th className="text-left px-4 py-3 text-sm text-gray-400 font-medium w-28">状态</th>
                    <th className="text-left px-4 py-3 text-sm text-gray-400 font-medium w-20">Chunk</th>
                    <th className="text-right px-4 py-3 text-sm text-gray-400 font-medium w-32">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((file) => {
                    const st = STATUS_CONFIG[file.type];
                    return (
                      <tr key={file.tag} className="border-b border-dark-border last:border-0 hover:bg-dark-hover">
                        {isAdmin && (
                          <td className="px-3 py-3">
                            <input
                              type="checkbox"
                              checked={file.tag in selected}
                              onChange={() => toggleFile(file.tag, file.type)}
                              className="rounded border-gray-600"
                            />
                          </td>
                        )}
                        <td className="px-4 py-3 overflow-hidden">
                          <div className="flex items-center gap-2 text-sm min-w-0">
                            <FileText size={14} className="text-gray-500 shrink-0" />
                            <span className="truncate block" title={file.name}>{file.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs border whitespace-nowrap ${st.color}`}>
                            {st.icon}
                            {st.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-400">{file.chunk_count || '-'}</td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            {isPdf(file) && (
                              <button
                                onClick={() => setPreviewFile(file.tag)}
                                className="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-dark-hover"
                                title="预览"
                              >
                                <Eye size={14} />
                              </button>
                            )}
                            {isAdmin && (
                              <button
                                onClick={() => handleDelete(file.tag)}
                                className="p-1.5 rounded-md text-gray-500 hover:text-red-400 hover:bg-dark-hover"
                                title="删除"
                              >
                                <Trash2 size={14} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-center gap-4 mt-4">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-2 rounded-lg hover:bg-dark-hover text-gray-400 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronLeft size={18} />
              </button>
              <span className="text-sm text-gray-400">
                第 {currentPage} / {totalPages} 页
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-2 rounded-lg hover:bg-dark-hover text-gray-400 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </>
        )}

        {/* Preview modal */}
        {previewFile && (
          <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-6" onClick={() => setPreviewFile(null)}>
            <div className="w-full max-w-4xl h-[85vh] bg-dark-card rounded-xl overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border">
                <span className="text-sm text-gray-300 truncate">{previewFile.split('/').pop()}</span>
                <button onClick={() => setPreviewFile(null)} className="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-dark-hover">
                  <X size={18} />
                </button>
              </div>
              <div className="flex-1 p-4">
                {previewLoading ? (
                  <div className="w-full h-full flex items-center justify-center text-gray-400 gap-3">
                    <Loader2 size={18} className="animate-spin" />
                    <span>正在加载预览...</span>
                  </div>
                ) : previewError ? (
                  <div className="w-full h-full flex items-center justify-center text-red-400">{previewError}</div>
                ) : previewUrl ? (
                  <iframe src={previewUrl} className="w-full h-full rounded-lg" title="文件预览" />
                ) : null}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
