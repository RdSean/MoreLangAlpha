import { Activity, BookOpenCheck, ChevronRight, Library } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useManagedTextbookLibrary } from './queries';
import type { BookStructureStatus } from './types';

const STRUCTURE_STATUS: Record<BookStructureStatus, string> = {
  queued: '等待结构分析',
  running: '正在分析结构',
  ready: '结构已就绪',
  failed: '结构分析失败',
};

export default function TextbooksPage() {
  const library = useManagedTextbookLibrary();
  const textbooks = library.data ?? [];

  return (
    <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="textbook-library-page">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between" style={{ borderColor: 'var(--color-border-muted)' }}>
          <div>
            <h1 className="text-2xl font-semibold text-foreground">教材</h1>
            <p className="mt-1 text-sm text-muted-foreground">阅读原文与讲义，生成内容和查看处理活动都在教材工作台完成。</p>
          </div>
          <Link
            to="/documents?useAsTextbook=1"
            className="inline-flex min-h-10 self-start items-center justify-center rounded-md bg-[var(--color-btn-primary-bg)] px-4 py-2 text-sm font-medium text-[var(--color-btn-primary-text)] hover:opacity-90 sm:self-auto"
          >
            <Library className="mr-2 size-4" aria-hidden="true" />
            从图书馆添加
          </Link>
        </header>

        {library.isLoading ? (
          <p className="py-8 text-sm text-muted-foreground">正在加载教材…</p>
        ) : textbooks.length === 0 ? (
          <section className="border-y py-12 text-center" style={{ borderColor: 'var(--color-border-muted)' }}>
            <BookOpenCheck className="mx-auto size-6 text-muted-foreground" aria-hidden="true" />
            <p className="mt-3 text-sm text-muted-foreground">尚未添加教材。</p>
            <Link className="mt-4 inline-flex min-h-11 items-center text-sm font-medium underline underline-offset-4" to="/documents?useAsTextbook=1">
              从图书馆选择来源
            </Link>
          </section>
        ) : (
          <div className="overflow-x-auto border-y" style={{ borderColor: 'var(--color-border-muted)' }}>
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="px-3 py-3 font-medium">教材</th>
                  <th scope="col" className="px-3 py-3 font-medium">结构</th>
                  <th scope="col" className="px-3 py-3 font-medium">讲义</th>
                  <th scope="col" className="px-3 py-3 font-medium">处理活动</th>
                  <th scope="col" className="px-3 py-3"><span className="sr-only">打开教材</span></th>
                </tr>
              </thead>
              <tbody>
                {textbooks.map((textbook) => (
                  <tr key={textbook.textbook_id} className="border-t" style={{ borderColor: 'var(--color-border-muted)' }}>
                    <td className="px-3 py-4 font-medium text-foreground">{textbook.title}</td>
                    <td className="px-3 py-4 text-muted-foreground">{STRUCTURE_STATUS[textbook.structure_status]}</td>
                    <td className="px-3 py-4 tabular-nums text-muted-foreground">
                      {textbook.materials.ready} / {textbook.materials.total}
                    </td>
                    <td className="px-3 py-4">
                      {textbook.current_job ? (
                        <Link
                          to={`/textbooks/${textbook.textbook_id}?activity=${textbook.current_job.job_id}`}
                          className="inline-flex min-h-10 items-center gap-2 rounded-md px-2 text-muted-foreground hover:bg-[var(--color-bg-hover)] hover:text-foreground"
                          aria-label={`查看 ${textbook.title} 的处理活动`}
                        >
                          <Activity className="size-4" aria-hidden="true" />
                          {textbook.current_job.status === 'queued' ? '等待开始' : '处理中'}
                        </Link>
                      ) : <span className="text-muted-foreground">无进行中任务</span>}
                    </td>
                    <td className="px-3 py-4 text-right">
                      <Link
                        to={`/textbooks/${textbook.textbook_id}`}
                        aria-label={`打开 ${textbook.title}`}
                        className="inline-flex size-11 items-center justify-center rounded-md text-muted-foreground hover:bg-[var(--color-bg-hover)] hover:text-foreground"
                      >
                        <ChevronRight className="size-4" aria-hidden="true" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
