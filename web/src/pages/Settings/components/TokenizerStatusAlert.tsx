import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Download, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  getTokenizerResourceStatus,
  retryTokenizerVocabularyDownload,
} from '@/api/model';
import { Button } from '@/components/ui/button';
import { queryKeys } from '@/lib/queryKeys';

export function TokenizerStatusAlert() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: queryKeys.runtimeResources.tokenizer(),
    queryFn: getTokenizerResourceStatus,
    retry: false,
  });
  const retryDownload = useMutation({
    mutationFn: retryTokenizerVocabularyDownload,
    onSuccess: (status) => {
      queryClient.setQueryData(queryKeys.runtimeResources.tokenizer(), status);
    },
  });

  if (!statusQuery.data || statusQuery.data.exact) return null;

  return (
    <div
      role="alert"
      className="flex flex-col gap-3 border px-4 py-3 sm:flex-row sm:items-start sm:justify-between"
      style={{
        backgroundColor: 'var(--color-loss-soft)',
        borderColor: 'var(--color-loss)',
        color: 'var(--color-loss)',
      }}
    >
      <div className="flex min-w-0 items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-semibold">{t('settings.tokenizerUnavailableTitle')}</p>
          <p className="mt-1 text-sm leading-5">{t('settings.tokenizerUnavailableDesc')}</p>
          {retryDownload.isError && (
            <p className="mt-1 text-xs font-medium">{t('settings.tokenizerDownloadFailed')}</p>
          )}
        </div>
      </div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="shrink-0"
        disabled={retryDownload.isPending}
        onClick={() => retryDownload.mutate()}
      >
        {retryDownload.isPending ? (
          <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />
        ) : (
          <Download className="mr-2 size-4" aria-hidden="true" />
        )}
        {retryDownload.isPending
          ? t('settings.tokenizerDownloading')
          : t('settings.tokenizerDownloadAction')}
      </Button>
    </div>
  );
}
