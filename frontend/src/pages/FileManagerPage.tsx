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
  ArrowUpFromLine,
} from 'lucide-react';

const PAGE_SIZE = 10;

const STATUS_CONFIG: Record<FileType, { label: string; icon: React.ReactNode; color: string; rowClass: string }> = {
  imported: {
    label: '已入库',
    icon: <CheckCircle size={12} />,
    color: 'text-emerald-400',
    rowClass: 'file-row-imported',
  },
  not_imported: {
    label: '待处理',
    icon: <AlertCircle size={12} />,
    color: 'text-amber-400',
    rowClass: 'file-row-not_imported',
  },
  ghost: {
    label: '残留',
    icon: <XCircle size={12} />,
    color: 'text-red-400',
    rowClass: 'file-row-ghost',
  },
};

export function FileManagerPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  const [files, setFiles] = useState<FileInfo[]>([]);
  const [totalPages, setTotalPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  const [stats, setStats] = useState({ imported: 0, not_imported: 0, ghost: 0 });
  const [loading, setLoading] = useState(true);

  const [searchQuery, setSearchQuery] = useState('');
  const deferredSearch = useDeferredValue(searchQuery.trim());
  const [filterType, setFilterType] = useState<string>('');

  const [selected, setSelected] = useState<Record<string, FileType>>({});
  const selectedCount = Object.keys(selected).length;
  const importableTags = Object.entries(selected).filter(([, t]) => t === 'not_imported').map(([tag]) => tag);
  const importableCount = importableTags.length;

  const [uploading, setUploading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importJob, setImportJob] = useState<FileImportResponse | null>(null);
  const [loadingAll, setLoadingAll] = useState(false);

  const [previewFile, setPreviewFile] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const fetchFiles = useCallback(
    async (page = currentPage, type = filterType, search = deferredSearch, forceRefresh = false) => {
      setLoading(true);
      try {
        const res = await fileApi.getFiles(page, PAGE_SIZE, type || undefined, search || undefined, forceRefresh);
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

  useEffect(() => {
    fetchFiles(currentPage, filterType, deferredSearch);
    setSelected({});
  }, [currentPage, filterType, deferredSearch]);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    fileApi.getActiveImportJob().then((job) => {
      if (!cancelled && ['queued', 'running'].includes(job.status)) setImportJob(job);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [isAdmin]);

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
          await fetchFiles(1, filterType, deferredSearch, true);
        }
      } catch {
        clearInterval(interval);
        setImporting(false);
      }
    }, 2000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [importJob?.job_id, importJob?.status]);

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
      if (!cancelled) setPreviewError('加载失败');
    }).finally(() => {
      if (!cancelled) setPreviewLoading(false);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [previewFile]);

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
        for (const file of Array.from(fileList)) await fileApi.uploadFile(file);
        setCurrentPage(1);
        setFilterType('not_imported');
        await fetchFiles(1, 'not_imported', deferredSearch, true);
      } catch (err) {
        console.error('Upload failed:', err);
      } finally {
        setUploading(false);
      }
    };
    input.click();
  }, [fetchFiles, deferredSearch]);

  const handleImport = useCallback(async () => {
    if (importableCount === 0) { alert('请选择待处理文件'); return; }
    if (!confirm(`导入 ${importableCount} 个文件？`)) return;
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
    if (!confirm('删除此文件？')) return;
    try {
      await fileApi.deleteFile(tag);
      await fetchFiles(currentPage, filterType, deferredSearch, true);
    } catch (err) {
      console.error('Delete failed:', err);
    }
  }, [currentPage, deferredSearch, fetchFiles, filterType]);

  const handleBatchDelete = useCallback(async () => {
    const tags = Object.keys(selected);
    if (tags.length === 0) return;
    if (!confirm(`删除 ${tags.length} 个文件？`)) return;
    try {
      await fileApi.deleteFiles({ file_tags: tags });
      setSelected({});
      await fetchFiles(currentPage, filterType, deferredSearch, true);
    } catch (err) {
      console.error('Batch delete failed:', err);
    }
  }, [currentPage, deferredSearch, selected, fetchFiles, filterType]);

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
    <div className="h-full overflow-y-auto custom-scrollbar p-4 lg:p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-lg font-medium text-white">文件管理</h1>
          {isAdmin && (
            <button onClick={handleUpload} disabled={uploading} className="btn btn-primary flex items-center gap-2">
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              上传
            </button>
          )}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-2 mb-4">
          <div className="card text-center py-3">
            <div className="text-lg font-medium text-white">{stats.imported + stats.not_imported}</div>
            <div className="text-xs text-zinc-500">文件</div>
          </div>
          <div className="card text-center py-3">
            <div className="text-lg font-medium text-emerald-400">{stats.imported}</div>
            <div className="text-xs text-zinc-500">已入库</div>
          </div>
          <div className="card text-center py-3">
            <div className="text-lg font-medium text-amber-400">{stats.not_imported}</div>
            <div className="text-xs text-zinc-500">待处理</div>
          </div>
          <div className="card text-center py-3">
            <div className="text-lg font-medium text-red-400">{stats.ghost}</div>
            <div className="text-xs text-zinc-500">残留</div>
          </div>
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-2 mb-3">
          {isAdmin && importableCount > 0 && (
            <button onClick={handleImport} disabled={importing} className="btn btn-secondary flex items-center gap-2">
              {importing ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
              导入 ({importableCount})
            </button>
          )}
          {isAdmin && selectedCount > 0 && (
            <button onClick={handleBatchDelete} className="btn btn-secondary text-red-400 flex items-center gap-2">
              <Trash2 size={14} />
              删除 ({selectedCount})
            </button>
          )}
          <div className="flex-1" />
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
              placeholder="搜索..."
              className="pl-9 pr-3 py-2 text-sm rounded-xl bg-zinc-800/50 border border-white/[0.04] outline-none text-zinc-300 placeholder-zinc-500 focus:bg-zinc-800 focus:border-white/[0.08] w-40 transition-all"
            />
          </div>
          <select
            value={filterType}
            onChange={(e) => { setFilterType(e.target.value); setCurrentPage(1); }}
            className="py-2 text-sm rounded-xl bg-zinc-800/50 border border-white/[0.04] outline-none text-zinc-300"
          >
            <option value="">全部</option>
            <option value="imported">已入库</option>
            <option value="not_imported">待处理</option>
            <option value="ghost">残留</option>
          </select>
          <button onClick={() => fetchFiles(currentPage, filterType, deferredSearch, true)} className="p-2 rounded-xl text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 transition-colors">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>

        {/* Import progress */}
        {importJob && ['queued', 'running'].includes(importJob.status) && (
          <div className="mb-3 px-4 py-3 rounded-xl bg-primary-500/10 border border-primary-500/10 text-sm">
            <div className="flex justify-between">
              <span className="text-zinc-300">索引任务：{importJob.status === 'queued' ? '排队' : '执行'}</span>
              <span className="text-zinc-400">{importJob.current_index}/{importJob.total}</span>
            </div>
          </div>
        )}

        {/* File list */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={20} className="animate-spin text-zinc-500" />
          </div>
        ) : files.length === 0 ? (
          <div className="text-center py-16 text-zinc-500">
            {isAdmin ? (
              <div className="border-2 border-dashed border-zinc-700 rounded-2xl p-10 max-w-md mx-auto hover:border-zinc-500 transition-colors cursor-pointer" onClick={handleUpload}>
                <ArrowUpFromLine size={36} className="mx-auto mb-3 opacity-40" />
                <p className="text-zinc-400 mb-1">拖拽文件到此处或点击上传</p>
                <p className="text-xs text-zinc-600">支持 PDF、DOC、DOCX、TXT、MD</p>
              </div>
            ) : (
              <>
                <FileText size={32} className="mx-auto mb-2 opacity-50" />
                <p>{deferredSearch ? '无匹配文件' : '暂无文件'}</p>
              </>
            )}
          </div>
        ) : (
          <>
            {isAdmin && files.length > 0 && (
              <div className="flex items-center gap-3 mb-2 text-xs text-zinc-500">
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={currentPageAllSelected} onChange={toggleSelectAll} className="accent-primary-500" />
                  <span>全选</span>
                </label>
                {selectedCount <= files.length && totalPages > 1 && (
                  <button onClick={selectAllPages} disabled={loadingAll} className="hover:text-zinc-300">
                    {loadingAll ? '...' : '全选所有页'}
                  </button>
                )}
                {selectedCount > 0 && (
                  <button onClick={clearSelection} className="hover:text-zinc-300">
                    清除 ({selectedCount})
                  </button>
                )}
              </div>
            )}

            <div className="card overflow-hidden divide-y divide-zinc-800/50">
              {files.map((file) => {
                const st = STATUS_CONFIG[file.type];
                return (
                  <div key={file.tag} className={`flex items-center gap-3 px-3 py-2.5 hover:bg-zinc-800/30 transition-colors ${st.rowClass}`}>
                    {isAdmin && (
                      <input
                        type="checkbox"
                        checked={file.tag in selected}
                        onChange={() => toggleFile(file.tag, file.type)}
                        className="accent-primary-500"
                      />
                    )}
                    <FileText size={16} className="text-zinc-500" />
                    <span className="flex-1 truncate text-sm text-zinc-200">{file.name}</span>
                    <span className={`flex items-center gap-1 text-xs ${st.color}`}>
                      {st.icon}
                      {st.label}
                    </span>
                    <span className="text-xs text-zinc-500 w-8">{file.chunk_count || '-'}</span>
                    <div className="flex items-center gap-1">
                      {isPdf(file) && (
                        <button onClick={() => setPreviewFile(file.tag)} className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50">
                          <Eye size={14} />
                        </button>
                      )}
                      {isAdmin && (
                        <button onClick={() => handleDelete(file.tag)} className="p-1.5 rounded-lg text-zinc-400 hover:text-red-400 hover:bg-zinc-800/50">
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-center gap-4 mt-4 text-sm text-zinc-400">
              <button onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={currentPage === 1} className="p-1.5 rounded-lg hover:bg-zinc-800/50 disabled:opacity-30">
                <ChevronLeft size={16} />
              </button>
              <span>{currentPage} / {totalPages}</span>
              <button onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="p-1.5 rounded-lg hover:bg-zinc-800/50 disabled:opacity-30">
                <ChevronRight size={16} />
              </button>
            </div>
          </>
        )}

        {/* Preview modal */}
        {previewFile && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 modal-overlay-enter" onClick={() => setPreviewFile(null)}>
            <div className="w-full max-w-3xl h-[80vh] card-glass flex flex-col overflow-hidden modal-enter" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800/50">
                <span className="text-sm text-zinc-300 truncate">{previewFile.split('/').pop()}</span>
                <button onClick={() => setPreviewFile(null)} className="p-1 rounded-lg text-zinc-400 hover:text-white transition-colors">
                  <X size={16} />
                </button>
              </div>
              <div className="flex-1 p-3">
                {previewLoading ? (
                  <div className="flex items-center justify-center h-full text-zinc-400">
                    <Loader2 size={16} className="animate-spin" />
                  </div>
                ) : previewError ? (
                  <div className="flex items-center justify-center h-full text-red-400">{previewError}</div>
                ) : previewUrl ? (
                  <iframe src={previewUrl} className="w-full h-full rounded-lg" title="预览" />
                ) : null}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
