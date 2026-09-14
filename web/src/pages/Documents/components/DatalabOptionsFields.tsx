import { useTranslation } from 'react-i18next';
import type { DatalabOptions, DatalabMode } from '../types';

interface DatalabOptionsFieldsProps {
  value: DatalabOptions;
  onChange: (next: DatalabOptions) => void;
}

const MODES: DatalabMode[] = ['fast', 'balanced', 'accurate'];

/**
 * Advanced knobs for the hosted Datalab parser.
 *
 * Collapsed by default and, more importantly, **only sends what the user
 * changed**. A control left at its default is omitted from `parser_options`
 * rather than sent explicitly, so a later change to the server-side default is
 * not silently overridden by a wizard that was loaded before it.
 *
 * The server validates the same fields with a Pydantic model
 * (`providers/datalab_options.py`) and ignores keys it does not know, so the
 * two can drift one release apart without either side breaking. Pinning them
 * together is the request-shape gap the artifact-contract work identified; it
 * is deliberately deferred rather than half-done here.
 */
export default function DatalabOptionsFields({
  value,
  onChange,
}: DatalabOptionsFieldsProps) {
  const { t } = useTranslation();

  /** Set a key, or drop it when the control returns to its default. */
  const patch = <K extends keyof DatalabOptions>(
    key: K,
    next: DatalabOptions[K] | undefined,
  ) => {
    const draft = { ...value };
    if (next === undefined) delete draft[key];
    else draft[key] = next;
    onChange(draft);
  };

  return (
    <details className="documents-advanced-options" data-testid="datalab-options">
      <summary>{t('documents.wizard.datalab.advanced')}</summary>

      <label className="documents-advanced-options__field">
        <span>{t('documents.wizard.datalab.mode')}</span>
        <select
          value={value.mode ?? 'balanced'}
          onChange={(event) => {
            const mode = event.target.value as DatalabMode;
            patch('mode', mode === 'balanced' ? undefined : mode);
          }}
        >
          {MODES.map((mode) => (
            <option key={mode} value={mode}>
              {t(`documents.wizard.datalab.mode_${mode}`)}
            </option>
          ))}
        </select>
      </label>

      <label className="documents-advanced-options__field">
        <span>{t('documents.wizard.datalab.pageRange')}</span>
        <input
          type="text"
          inputMode="numeric"
          placeholder="0-5,10"
          value={value.page_range ?? ''}
          onChange={(event) => patch('page_range', event.target.value || undefined)}
        />
        <small>{t('documents.wizard.datalab.pageRangeHint')}</small>
      </label>

      <label className="documents-advanced-options__field">
        <input
          type="checkbox"
          checked={value.paginate ?? true}
          onChange={(event) => patch('paginate', event.target.checked ? undefined : false)}
        />
        <span>{t('documents.wizard.datalab.paginate')}</span>
      </label>

      <label className="documents-advanced-options__field">
        <input
          type="checkbox"
          checked={value.token_efficient_markdown ?? false}
          onChange={(event) =>
            patch('token_efficient_markdown', event.target.checked ? true : undefined)
          }
        />
        <span>{t('documents.wizard.datalab.tokenEfficient')}</span>
      </label>

      <label className="documents-advanced-options__field">
        <input
          type="checkbox"
          checked={value.disable_image_extraction ?? true}
          onChange={(event) =>
            patch('disable_image_extraction', event.target.checked ? undefined : false)
          }
        />
        <span>{t('documents.wizard.datalab.imageExtraction')}</span>
        <small>{t('documents.wizard.datalab.imageExtractionHint')}</small>
      </label>
    </details>
  );
}
