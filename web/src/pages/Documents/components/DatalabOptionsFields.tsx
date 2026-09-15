import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Info } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { DatalabOptions, DatalabMode } from '../types';

interface DatalabOptionsFieldsProps {
  value: DatalabOptions;
  onChange: (next: DatalabOptions) => void;
}

const MODES: DatalabMode[] = ['fast', 'balanced', 'accurate'];

interface ToggleTileProps {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Rendered inside the tile when the explanation is short. */
  hint?: string;
  /** Rendered behind an info button when the explanation would crowd the tile. */
  tip?: string;
}

/**
 * One switch in the second row.
 *
 * The tip button is a sibling of the label rather than a child of it: a
 * `<button>` inside a `<label>` is invalid — a label may not contain another
 * labelable element — and clicking it would tick the checkbox on the way past.
 */
function ToggleTile({ id, label, checked, onChange, hint, tip }: ToggleTileProps) {
  return (
    <div className="documents-advanced-options__toggle">
      <label className="documents-advanced-options__toggle-label" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="documents-advanced-options__copy">
          <span>{label}</span>
          {hint && <small>{hint}</small>}
        </span>
      </label>

      {tip && (
        <TooltipProvider delayDuration={150}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="documents-advanced-options__tip"
                aria-label={`${label} — ${tip}`}
              >
                <Info className="size-3.5" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-[260px]">{tip}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  );
}

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
  const baseId = useId();

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

      {/* Two rows, each its own grid: the valued settings on top, the switches
          below. Laying them out as one column of five mixed controls is what
          made this panel look ragged — a checkbox, a select and a text field
          have three different heights and nothing lined up. */}
      <div
        className="documents-advanced-options__row documents-advanced-options__row--fields"
        data-testid="datalab-options-fields"
      >
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
      </div>

      <div
        className="documents-advanced-options__row documents-advanced-options__row--toggles"
        data-testid="datalab-options-toggles"
      >
        <ToggleTile
          id={`${baseId}-paginate`}
          label={t('documents.wizard.datalab.paginate')}
          checked={value.paginate ?? true}
          onChange={(checked) => patch('paginate', checked ? undefined : false)}
        />

        <ToggleTile
          id={`${baseId}-token-efficient`}
          label={t('documents.wizard.datalab.tokenEfficient')}
          checked={value.token_efficient_markdown ?? false}
          onChange={(checked) =>
            patch('token_efficient_markdown', checked ? true : undefined)
          }
        />

        <ToggleTile
          id={`${baseId}-image-extraction`}
          label={t('documents.wizard.datalab.imageExtraction')}
          /* The wire field is negative and this label is positive, so the box
             is ticked unless the user explicitly turned extraction off. (It
             used to be bound straight to the flag, which rendered "Extract
             images" as checked while the server skipped every image.) */
          checked={value.disable_image_extraction !== true}
          onChange={(checked) =>
            patch('disable_image_extraction', checked ? undefined : true)
          }
          hint={t('documents.wizard.datalab.imageExtractionHint')}
        />

        <ToggleTile
          id={`${baseId}-image-captions`}
          /* Negative label for a negative field, so the checkbox shows the
             truth: ticked means captions are off, which is the default. */
          label={t('documents.wizard.datalab.imageCaptions')}
          checked={value.disable_image_captions ?? true}
          onChange={(checked) => patch('disable_image_captions', checked ? undefined : false)}
          tip={t('documents.wizard.datalab.imageCaptionsTip')}
        />
      </div>
    </details>
  );
}
