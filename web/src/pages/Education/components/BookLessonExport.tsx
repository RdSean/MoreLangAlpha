import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Download, FileText, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ui/loader';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { downloadBookLessonPdf } from '../api';

export function BookLessonExport({ textbookId, knowledgePointId, assignmentId, markdown, questionsBusy = false }: {
  textbookId: string; knowledgePointId: string; assignmentId?: string; markdown: string; questionsBusy?: boolean;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const download = async (includeQuestions: boolean) => {
    if (controller.current || (includeQuestions && questionsBusy)) return;
    const abort = new AbortController();
    controller.current = abort;
    setPending(true);
    setError('');
    try {
      await downloadBookLessonPdf({ textbookId, knowledgePointId, assignmentId, markdown, includeQuestions, signal: abort.signal });
    } catch (failure) {
      if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : 'PDF 导出失败，请重试。');
    } finally {
      controller.current = null;
      if (!abort.signal.aborted) setPending(false);
    }
  };

  return <div className="relative shrink-0">
    <div className="flex items-center" role="group" aria-label="导出 PDF" aria-busy={pending}>
      <Button variant="outline" className="h-11 rounded-r-none gap-1.5 px-2.5 sm:h-8 text-xs" title="导出讲义 PDF" aria-label="导出讲义 PDF" disabled={pending} onClick={() => void download(false)}>
        {pending ? <Loader /> : <Download className="size-4" aria-hidden="true" />}<span>{pending ? '正在导出' : '导出 PDF'}</span>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild><Button variant="outline" className="h-11 w-11 rounded-l-none border-l-0 px-0 sm:h-8 sm:w-8" aria-label="PDF 导出选项" title="PDF 导出选项" disabled={pending}><ChevronDown className="size-4" aria-hidden="true" /></Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem className="min-h-11 sm:min-h-8" onSelect={() => void download(false)}><FileText className="size-4" aria-hidden="true" />仅讲义</DropdownMenuItem>
          <DropdownMenuItem className="min-h-11 sm:min-h-8" disabled={questionsBusy} onSelect={() => void download(true)}><MessageSquare className="size-4" aria-hidden="true" />讲义及我的问答</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
    {error && <p role="alert" className="mt-2 max-w-64 text-xs text-destructive">{error}</p>}
  </div>;
}
