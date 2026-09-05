import { AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import type { ParserOption } from '../../types';

interface MethodStepProps {
  options: ParserOption[];
  selectedParserId: string;
  pending: boolean;
  error?: string;
  onSelect: (parserId: string) => void;
  onBack: () => void;
  onStart: () => void;
}

export default function MethodStep({
  options,
  selectedParserId,
  pending,
  error,
  onSelect,
  onBack,
  onStart,
}: MethodStepProps) {
  const { t } = useTranslation();
  const selected = options.find((option) => option.parser_id === selectedParserId);

  return (
    <div className="documents-wizard-step">
      <div>
        <h2>{t('documents.wizard.method.title')}</h2>
        <p>{t('documents.wizard.method.subtitle')}</p>
      </div>

      <fieldset className="documents-parser-options">
        <legend className="sr-only">{t('documents.wizard.method.title')}</legend>
        {options.map((option) => (
          <label key={option.parser_id} className={`documents-parser-option${option.available ? '' : ' is-disabled'}`}>
            <input
              type="radio"
              name="document-parser"
              value={option.parser_id}
              checked={selectedParserId === option.parser_id}
              disabled={!option.available}
              onChange={() => onSelect(option.parser_id)}
            />
            <span className="documents-parser-copy">
              <span className="documents-parser-heading">
                <strong>{option.display_name}</strong>
                {option.version && <code>v{option.version}</code>}
                {option.recommended && <small>{t('documents.wizard.method.recommended')}</small>}
                {!option.available && <small>{t('documents.wizard.method.unavailable')}</small>}
              </span>
              <span>{option.reason}</span>
              {option.warning && (
                <span className="documents-parser-warning">
                  <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                  {option.warning}
                </span>
              )}
            </span>
          </label>
        ))}
      </fieldset>

      {error && <p className="documents-wizard-error" role="alert">{error}</p>}
      <div className="documents-wizard-actions documents-wizard-actions--split">
        <Button type="button" variant="ghost" onClick={onBack}>{t('documents.wizard.actions.back')}</Button>
        <Button type="button" disabled={pending || !selected?.available} onClick={onStart}>
          {pending ? t('documents.wizard.method.starting') : t('documents.wizard.method.start')}
        </Button>
      </div>
    </div>
  );
}
