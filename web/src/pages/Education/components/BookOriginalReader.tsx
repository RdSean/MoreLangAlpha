import { lazy, Suspense, useCallback, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import DocumentErrorBoundary from '@/pages/ChatAgent/components/viewers/DocumentErrorBoundary';
import { useManagedBookOriginal, useManagedBookOriginalLocation } from '../queries';

const PdfViewer = lazy(() => import('@/pages/ChatAgent/components/viewers/PdfViewer'));

interface Props {
  textbookId: string;
  startLine?: number;
  jsonPage?: number;
  restoredPage?: number;
  onPageChange?: (page: number) => void;
  keyboardScope?: 'document' | 'viewer';
}

export function BookOriginalReader({ textbookId, startLine, jsonPage, restoredPage, onPageChange, keyboardScope = 'document' }: Props) {
  const { t } = useTranslation();
  const original = useManagedBookOriginal(textbookId);
  const location = useManagedBookOriginalLocation(textbookId, startLine);
  const [manualPage, setManualPage] = useState<number>();
  const [pageCount, setPageCount] = useState<number>();
  const [reload, setReload] = useState(0);
  const selectedPage = manualPage ?? restoredPage ?? location.data?.page ?? jsonPage ?? 1;
  const page = pageCount && selectedPage > pageCount ? 1 : selectedPage;
  const handlePageChange = useCallback((next: number) => {
    setManualPage(next);
    onPageChange?.(next);
  }, [onPageChange]);
  const handlePageCount = useCallback((count: number) => setPageCount(count), []);
  const error = (
    <div className="grid h-full place-content-center justify-items-center gap-4 p-6 text-center">
      <p role="alert" className="text-sm text-muted-foreground">{t('bookProcessing.originalUnavailable')}</p>
      <Button variant="outline" className="min-h-11" onClick={() => { setReload((value) => value + 1); void original.refetch(); }}>
        <RefreshCw className="mr-2 size-4" aria-hidden="true" />{t('common.retry')}
      </Button>
    </div>
  );
  if (original.isError) return error;
  if (!original.data) return <p role="status" className="p-6 text-sm text-muted-foreground">{t('bookProcessing.originalLoading')}</p>;
  if (!original.data.mediaType.includes('pdf')) return error;
  return (
    <div className="book-original-reader h-full min-h-0" aria-label={t('bookProcessing.originalFile')}>
      <DocumentErrorBoundary key={`${textbookId}:${reload}`} fallback={error}>
        <Suspense fallback={<p role="status" className="p-6 text-sm text-muted-foreground">{t('bookProcessing.originalLoading')}</p>}>
          <PdfViewer data={original.data.bytes} viewMode="single" pageNumber={page} onPageChange={handlePageChange} onNumPagesChange={handlePageCount} fitPage pageNavigation keyboardScope={keyboardScope} />
        </Suspense>
      </DocumentErrorBoundary>
    </div>
  );
}
