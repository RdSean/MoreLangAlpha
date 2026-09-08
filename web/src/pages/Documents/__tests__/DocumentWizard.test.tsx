import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '@/contexts/ThemeContext';
import type { Artifact, DocumentSummary, InspectionOutcome, ParseJob } from '../types';

const uploadDocument = { mutateAsync: vi.fn(), isPending: false };
const inspectDocument = { mutateAsync: vi.fn(), isPending: false };
const createParseJob = { mutateAsync: vi.fn(), isPending: false };
const cancelJob = { mutateAsync: vi.fn(), isPending: false };
const createDataset = { mutateAsync: vi.fn(), isPending: false };
const useDocument = vi.fn();
const useDocumentJobs = vi.fn();
const watchDocumentJob = vi.fn();
const listDocumentArtifacts = vi.fn();
const fetchArtifactText = vi.fn();

vi.mock('../hooks', () => ({
  useDocument: (...args: unknown[]) => useDocument(...args),
  useDocumentDatasets: () => ({ data: { items: [
    { dataset_id: 'dts-math1234567', name: 'Mathematics', document_count: 0 },
    { dataset_id: 'dts-language123', name: 'Language', document_count: 0 },
  ], total: 2 } }),
  useDocumentTags: () => ({ data: [] }),
  useDocumentJobs: (...args: unknown[]) => useDocumentJobs(...args),
  useDocumentMutations: () => ({ uploadDocument, inspectDocument, createParseJob, cancelJob, createDataset }),
}));

vi.mock('../api', () => ({
  watchDocumentJob: (...args: unknown[]) => watchDocumentJob(...args),
  listDocumentArtifacts: (...args: unknown[]) => listDocumentArtifacts(...args),
  fetchArtifactText: (...args: unknown[]) => fetchArtifactText(...args),
  artifactDownloadUrl: (artifactId: string) => `/api/v1/document-artifacts/${artifactId}/download`,
}));

import DocumentWizard from '../components/DocumentWizard';

const document: DocumentSummary = {
  document_id: 'doc-A1b2C3d4E5f6',
  original_filename: 'Algebra handbook.pdf',
  media_type: 'application/pdf',
  document_format: 'pdf',
  source_size_bytes: 1_572_864,
  source_sha256: 'abc',
  datasets: [],
  tags: [],
};

const outcome: InspectionOutcome = {
  inspection: {
    inspection_id: 'ins-A1b2C3d4E5f6',
    document_id: document.document_id,
    inspector_id: 'pdf-inspector',
    inspector_name: 'PDF Inspector',
    inspector_version: '1.17.0',
    status: 'completed',
    detected_format: 'pdf',
    classification: 'text_based',
    summary: {
      page_count: 12,
      page_dimensions: [{ page: 1, width_points: 595, height_points: 842 }],
    },
    details: {},
  },
  parser_options: [
    {
      parser_id: 'anydoc-local',
      display_name: 'AnyDoc Local',
      version: '0.2.4',
      supported_formats: ['pdf'],
      supported_classifications: ['text_based'],
      available: true,
      reason: 'Fast extraction for digital PDFs.',
      recommended: true,
    },
    {
      parser_id: 'ocr-document',
      display_name: 'OCR Document',
      supported_formats: ['pdf'],
      supported_classifications: ['mixed'],
      available: false,
      reason: 'OCR parser is not configured yet.',
      recommended: false,
    },
  ],
};

function parseJob(status: ParseJob['status'], version: number): ParseJob {
  return {
    job_id: 'job-A1b2C3d4E5f6',
    document_id: document.document_id,
    inspection_id: outcome.inspection.inspection_id,
    parser_id: 'anydoc-local',
    parser_name: 'AnyDoc Local',
    parser_version: '0.2.4',
    parser_options: {},
    request_mode: 'async',
    status,
    stage: status === 'completed' ? 'completed' : status === 'failed' ? 'failed' : 'parsing',
    percentage: status === 'completed' ? 100 : 45,
    status_version: version,
    attempt_count: 1,
  };
}

const markdownArtifact: Artifact = {
  artifact_id: 'art-A1b2C3d4E5f6',
  document_id: document.document_id,
  producer_job_id: 'job-A1b2C3d4E5f6',
  artifact_kind: 'primary_document',
  format: 'markdown',
  media_type: 'text/markdown',
  relative_path: 'document.md',
};

function renderWizard() {
  return render(
    <ThemeProvider>
      <DocumentWizard open onOpenChange={vi.fn()} />
    </ThemeProvider>,
  );
}

async function uploadAndInspect(user: ReturnType<typeof userEvent.setup>) {
  const file = new File(['%PDF-demo'], document.original_filename, { type: 'application/pdf' });
  await user.upload(screen.getByLabelText('PDF file'), file);
  await user.click(screen.getByRole('button', { name: 'Upload and inspect' }));
}

describe('DocumentWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useDocument.mockReturnValue({ data: undefined });
    useDocumentJobs.mockReturnValue({ data: [] });
    uploadDocument.mutateAsync.mockResolvedValue(document);
    inspectDocument.mutateAsync.mockResolvedValue(outcome);
    createParseJob.mutateAsync.mockResolvedValue({ job: parseJob('queued', 0), status: 202 });
    watchDocumentJob.mockResolvedValue(undefined);
    listDocumentArtifacts.mockResolvedValue([]);
    fetchArtifactText.mockResolvedValue('');
    createDataset.mutateAsync.mockResolvedValue({ dataset_id: 'dts-science1234', name: 'Science', document_count: 0 });
  });

  it('uses an empty multi-select and creates/selects a dataset from the split action', async () => {
    const user = userEvent.setup();
    renderWizard();

    expect(screen.getByRole('button', { name: 'Dataset selector' })).toHaveTextContent('No datasets selected');
    await user.click(screen.getByRole('button', { name: 'Dataset actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Create dataset' }));
    await user.type(screen.getByLabelText('Name'), 'Science');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(createDataset.mutateAsync).toHaveBeenCalledWith({ name: 'Science', description: null });
    expect(screen.getByRole('button', { name: 'Dataset selector' })).toHaveTextContent('Science');
  });

  it('uploads and inspects but does not start parsing', async () => {
    const user = userEvent.setup();
    renderWizard();

    await uploadAndInspect(user);

    expect(uploadDocument.mutateAsync).toHaveBeenCalledOnce();
    expect(inspectDocument.mutateAsync).toHaveBeenCalledWith(document.document_id);
    expect(createParseJob.mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByText(document.original_filename)).toBeInTheDocument();
    expect(screen.getByText('1.5 MB')).toBeInTheDocument();
    expect(await screen.findByText('12 pages')).toBeInTheDocument();
    expect(screen.getByText('595 × 842 pt')).toBeInTheDocument();
    expect(screen.getByText('Digital text')).toBeInTheDocument();
    expect(screen.getByText(/AnyDoc Local/)).toBeInTheDocument();
  });

  it.each(['mixed', 'scanned', 'image_based'] as const)(
    'keeps AnyDoc visible but incompatible for %s PDFs',
    async (classification) => {
      inspectDocument.mutateAsync.mockResolvedValue({
        ...outcome,
        inspection: { ...outcome.inspection, classification },
        parser_options: [
          {
            ...outcome.parser_options[0],
            available: false,
            recommended: false,
            reason: 'This PDF needs image-aware extraction.',
          },
          outcome.parser_options[1],
        ],
      });
      const user = userEvent.setup();
      renderWizard();
      await uploadAndInspect(user);
      await user.click(await screen.findByRole('button', { name: 'Choose method' }));

      expect(screen.getByRole('radio', { name: /AnyDoc Local/ })).toBeDisabled();
      expect(screen.getByText('This PDF needs image-aware extraction.')).toBeInTheDocument();
    },
  );

  it.each(['scanned', 'image_based'] as const)(
    'shows the legacy quality warning for %s PDFs',
    async (classification) => {
      inspectDocument.mutateAsync.mockResolvedValue({
        ...outcome,
        inspection: { ...outcome.inspection, classification },
        parser_options: [
          {
            parser_id: 'legacy-pdfplumber',
            display_name: 'Legacy PDF parser',
            version: '1',
            supported_formats: ['pdf'],
            supported_classifications: [classification],
            available: true,
            reason: 'Use the currently available local parser.',
            warning: 'Scanned content may produce incomplete text without OCR.',
            recommended: true,
          },
        ],
      });
      const user = userEvent.setup();
      renderWizard();
      await uploadAndInspect(user);
      await user.click(await screen.findByRole('button', { name: 'Choose method' }));

      expect(screen.getByText('Scanned content may produce incomplete text without OCR.')).toBeInTheDocument();
    },
  );

  it('requires an explicit available parser selection before starting', async () => {
    const user = userEvent.setup();
    renderWizard();
    await uploadAndInspect(user);
    await user.click(await screen.findByRole('button', { name: 'Choose method' }));

    expect(screen.getByRole('button', { name: 'Start parsing' })).toBeDisabled();
    expect(screen.getByRole('radio', { name: /OCR Document/ })).toBeDisabled();
    await user.click(screen.getByRole('radio', { name: /AnyDoc Local/ }));
    await user.click(screen.getByRole('button', { name: 'Start parsing' }));

    expect(createParseJob.mutateAsync).toHaveBeenCalledWith({
      documentId: document.document_id,
      input: {
        inspection_id: outcome.inspection.inspection_id,
        parser_id: 'anydoc-local',
        mode: 'async',
        options: {},
      },
    });
  });

  it('retries a failed inspection without uploading the source again', async () => {
    const failed = {
      ...outcome,
      inspection: { ...outcome.inspection, status: 'failed' as const, classification: 'unknown' as const },
      parser_options: [],
    };
    inspectDocument.mutateAsync.mockResolvedValueOnce(failed).mockResolvedValueOnce(outcome);
    const user = userEvent.setup();
    renderWizard();
    await uploadAndInspect(user);

    await user.click(await screen.findByRole('button', { name: 'Retry inspection' }));

    expect(uploadDocument.mutateAsync).toHaveBeenCalledOnce();
    expect(inspectDocument.mutateAsync).toHaveBeenCalledTimes(2);
    expect(await screen.findByText('12 pages')).toBeInTheDocument();
  });

  it('shows polling fallback and a terminal parser failure', async () => {
    watchDocumentJob.mockImplementation(async (_jobId, options) => {
      options.onError(new TypeError('stream disconnected'));
      options.onSnapshot({
        ...parseJob('failed', 2),
        error_message: 'The parser could not read this document.',
      });
    });
    const user = userEvent.setup();
    renderWizard();
    await uploadAndInspect(user);
    await user.click(await screen.findByRole('button', { name: 'Choose method' }));
    await user.click(screen.getByRole('radio', { name: /AnyDoc Local/ }));
    await user.click(screen.getByRole('button', { name: 'Start parsing' }));

    expect(await screen.findByText(/Progress is being checked periodically/)).toBeInTheDocument();
    expect(await screen.findByText('The parser could not read this document.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Choose another method' })).toBeEnabled();
  });

  it('cancels an active durable job and lets the user choose another method', async () => {
    cancelJob.mutateAsync.mockResolvedValue(parseJob('cancelled', 1));
    const user = userEvent.setup();
    renderWizard();
    await uploadAndInspect(user);
    await user.click(await screen.findByRole('button', { name: 'Choose method' }));
    await user.click(screen.getByRole('radio', { name: /AnyDoc Local/ }));
    await user.click(screen.getByRole('button', { name: 'Start parsing' }));
    await user.click(await screen.findByRole('button', { name: 'Cancel parsing' }));

    expect(cancelJob.mutateAsync).toHaveBeenCalledWith('job-A1b2C3d4E5f6');
    expect(await screen.findByText('Parsing cancelled')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Choose another method' })).toBeEnabled();
  });

  it('follows job snapshots to Markdown and keeps generic artifacts and prior runs', async () => {
    const imageArtifact: Artifact = {
      ...markdownArtifact,
      artifact_id: 'art-Z9y8X7w6V5u4',
      artifact_kind: 'embedded_image',
      format: 'png',
      media_type: 'image/png',
      relative_path: 'images/page-1.png',
    };
    const jsonArtifact: Artifact = {
      ...markdownArtifact,
      artifact_id: 'art-J1s2O3n4D5a6',
      artifact_kind: 'structured_data',
      format: 'json',
      media_type: 'application/json',
      relative_path: 'document.json',
    };
    const manifestArtifact: Artifact = {
      ...markdownArtifact,
      artifact_id: 'art-M1a2N3i4F5e6',
      artifact_kind: 'manifest',
      format: 'json',
      media_type: 'application/json',
      relative_path: 'manifest.json',
    };
    const priorJob = {
      ...parseJob('completed', 1),
      job_id: 'job-Z9y8X7w6V5u4',
      parser_id: 'legacy-pdfplumber',
      parser_name: 'Legacy PDF parser',
    };
    useDocumentJobs.mockReturnValue({ data: [parseJob('completed', 2), priorJob], refetch: vi.fn() });
    listDocumentArtifacts.mockResolvedValue([markdownArtifact, imageArtifact, jsonArtifact, manifestArtifact]);
    fetchArtifactText.mockResolvedValue('# Algebra\n\nExtracted lesson.');
    watchDocumentJob.mockImplementation(async (_jobId, options) => {
      options.onSnapshot(parseJob('running', 1));
      options.onSnapshot(parseJob('completed', 2));
    });
    const user = userEvent.setup();
    renderWizard();
    await uploadAndInspect(user);
    await user.click(await screen.findByRole('button', { name: 'Choose method' }));
    await user.click(screen.getByRole('radio', { name: /AnyDoc Local/ }));
    await user.click(screen.getByRole('button', { name: 'Start parsing' }));

    expect(await screen.findByRole('heading', { name: 'Algebra' })).toBeInTheDocument();
    expect(screen.getByText('images/page-1.png')).toBeInTheDocument();
    expect(screen.getByText('document.json')).toBeInTheDocument();
    expect(screen.getByText('manifest.json')).toBeInTheDocument();
    expect(screen.getByText('AnyDoc Local')).toBeInTheDocument();
    expect(screen.getByText('Legacy PDF parser')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Parse again' }));
    expect(screen.getByRole('button', { name: 'Start parsing' })).toBeDisabled();
  });
});
