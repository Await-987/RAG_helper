import { memo } from 'react';
import { FileText, Search, Target } from 'lucide-react';
import type { RetrievalTrace } from '@/types';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';

interface RetrievalTracePanelProps {
  traces: RetrievalTrace[];
}

export const RetrievalTracePanel = memo(function RetrievalTracePanel({ traces }: RetrievalTracePanelProps) {
  if (!traces || traces.length === 0) {
    return (
      <div
        className="mt-2 px-3 py-3 rounded-xl text-xs text-zinc-400"
        style={{ background: 'rgba(255,255,255,0.03)' }}
      >
        本轮没有触发知识库检索，或回答直接基于模型自有上下文。
      </div>
    );
  }

  const multi = traces.length > 1;

  return (
    <div
      className="mt-2 px-3 py-3 rounded-xl text-xs text-zinc-300 max-h-[55vh] overflow-y-auto custom-scrollbar"
      style={{ background: 'rgba(255,255,255,0.03)' }}
    >
      <div className="text-[11px] text-zinc-500 mb-2">
        {multi
          ? `本轮共进行了 ${traces.length} 次检索，下面按调用顺序列出每次的检索信息与新增的文本块。`
          : '本轮共进行了 1 次检索，下面展示本次的检索信息与命中的文本块。'}
      </div>

      <Accordion type="multiple" defaultValue={traces.map((_, i) => `trace-${i}`)} className="space-y-2">
        {traces.map((trace, i) => (
          <AccordionItem key={`trace-${i}`} value={`trace-${i}`} className="border border-zinc-800 rounded-lg bg-[rgba(255,255,255,0.02)]">
            <AccordionTrigger className="px-3 py-2 text-[11px] font-medium text-primary-400 hover:no-underline">
              {multi ? `第 ${i + 1} 次检索` : '检索详情'}
            </AccordionTrigger>
            <AccordionContent className="px-3 pb-3">
              <div className="flex items-start gap-2 mb-1.5">
                <Search size={12} className="mt-0.5 text-zinc-500 shrink-0" />
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-wide text-zinc-500">query · 召回关键词</div>
                  <div className="text-xs text-zinc-200 break-words">
                    {trace.query || <span className="text-zinc-500">（空）</span>}
                  </div>
                </div>
              </div>

              <div className="flex items-start gap-2 mb-2">
                <Target size={12} className="mt-0.5 text-zinc-500 shrink-0" />
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-wide text-zinc-500">
                    intent_description · 重排意图
                  </div>
                  <div className="text-xs text-zinc-200 break-words">
                    {trace.intent_description || <span className="text-zinc-500">（空）</span>}
                  </div>
                </div>
              </div>

              <div className="border-t border-zinc-800 pt-2">
                <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">
                  命中文本块（本次新增，已省略显示）
                </div>
                {trace.chunks && trace.chunks.length > 0 ? (
                  <ul className="flex flex-col gap-1.5">
                    {trace.chunks.map((chunk, idx) => (
                      <li
                        key={`${chunk.file_tag}-${idx}`}
                        className="px-2 py-1.5 rounded-md bg-zinc-900/50"
                      >
                        <div className="flex items-center gap-1.5 text-[11px] text-zinc-400 mb-1">
                          <FileText size={10} className="shrink-0" />
                          <span className="truncate">{chunk.label || chunk.file_tag || '未知来源'}</span>
                          {Number.isFinite(chunk.score) && chunk.score > 0 && (
                            <span className="ml-auto text-[10px] text-zinc-500 shrink-0">
                              score {chunk.score.toFixed(3)}
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-zinc-300 leading-relaxed whitespace-pre-wrap break-words">
                          {chunk.preview || <span className="text-zinc-500">（无文本预览）</span>}
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-[11px] text-zinc-500">本次调用未返回新的文本块。</div>
                )}
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
});