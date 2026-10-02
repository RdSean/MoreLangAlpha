import { ArrowLeft, RotateCcw } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function LegacyTextbookRouteReset() {
  return (
    <main className="grid h-full place-items-center bg-background px-4">
      <section className="w-full max-w-lg border-y py-10 text-center">
        <RotateCcw className="mx-auto size-6 text-muted-foreground" aria-hidden="true" />
        <h1 className="mt-4 text-lg font-semibold text-foreground">旧教材流程已重置</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          教材结构、讲义生成和处理活动现在都在教材工作台完成。
        </p>
        <Link
          to="/textbooks"
          className="mt-5 inline-flex min-h-11 items-center justify-center gap-2 rounded-md border px-4 text-sm font-medium hover:bg-[var(--color-bg-hover)]"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          返回教材列表
        </Link>
      </section>
    </main>
  );
}
