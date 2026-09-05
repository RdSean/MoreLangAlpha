import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import { useDocumentMutations } from '../hooks';
import type { DatasetSummary } from '../types';

interface DatasetDialogProps {
  dataset?: DatasetSummary;
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function DatasetDialog({ dataset, trigger, open, onOpenChange }: DatasetDialogProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const mutations = useDocumentMutations();
  const [internalOpen, setInternalOpen] = useState(false);
  const [name, setName] = useState(dataset?.name ?? '');
  const [description, setDescription] = useState(dataset?.description ?? '');
  const dialogOpen = open ?? internalOpen;
  const pending = dataset ? mutations.updateDataset.isPending : mutations.createDataset.isPending;

  useEffect(() => {
    if (!dialogOpen) return;
    setName(dataset?.name ?? '');
    setDescription(dataset?.description ?? '');
  }, [dataset, dialogOpen]);

  const setOpen = (next: boolean) => {
    setInternalOpen(next);
    onOpenChange?.(next);
  };

  const submit = async () => {
    const input = { name: name.trim(), description: description.trim() || null };
    try {
      if (dataset) {
        await mutations.updateDataset.mutateAsync({ datasetId: dataset.dataset_id, ...input });
      } else {
        await mutations.createDataset.mutateAsync(input);
      }
      setOpen(false);
    } catch {
      toast({
        variant: 'destructive',
        description: t(dataset ? 'documents.datasets.updateFailed' : 'documents.datasets.createFailed'),
      });
    }
  };

  return (
    <Dialog open={dialogOpen} onOpenChange={setOpen}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent variant="centered" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="title-font">
            {t(dataset ? 'documents.datasets.renameTitle' : 'documents.datasets.createTitle')}
          </DialogTitle>
        </DialogHeader>
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label className="grid gap-1.5 text-sm font-medium" htmlFor="dataset-name">
            {t('documents.datasets.name')}
            <Input
              id="dataset-name"
              value={name}
              maxLength={120}
              autoFocus
              required
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="grid gap-1.5 text-sm font-medium" htmlFor="dataset-description">
            {t('documents.datasets.description')}
            <textarea
              id="dataset-description"
              className="min-h-24 w-full resize-y rounded-md border bg-background px-3 py-2 text-base outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-sm"
              style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-primary)' }}
              value={description}
              maxLength={1000}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <DialogFooter>
            <Button type="submit" disabled={!name.trim() || pending}>
              {pending
                ? t('documents.actions.saving')
                : t(dataset ? 'documents.actions.save' : 'documents.actions.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
