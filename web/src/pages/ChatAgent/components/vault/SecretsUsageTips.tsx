import { useTranslation } from 'react-i18next';
import { Info } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

/**
 * The "what is this page for" explainer for the secrets surface.
 *
 * It lives beside {@link SecretsManager} rather than inside one page so the
 * copy has a single home: the two ports (Plugins → Secrets and a workspace's
 * Vault tab) describe the same idea at different scopes, and splitting the
 * wording per page is how the two drift apart.
 *
 * Two registers on purpose. The short sentence in the page header answers
 * "where does this go and who reads it"; this popover answers "when would I
 * actually use one", in the plainest terms the surface can get away with —
 * no reference syntax, no storage details, nothing a user has to decode.
 */
export function SecretsUsageTips() {
  const { t } = useTranslation();

  // Literal keys, not a template: the locale-parity sweep only sees statically
  // written t() calls, so a computed key would ship untranslated in silence.
  const scenarios = [
    {
      title: t('plugins.secrets.tips.scenario1Title'),
      body: t('plugins.secrets.tips.scenario1Body'),
    },
    {
      title: t('plugins.secrets.tips.scenario2Title'),
      body: t('plugins.secrets.tips.scenario2Body'),
    },
    {
      title: t('plugins.secrets.tips.scenario3Title'),
      body: t('plugins.secrets.tips.scenario3Body'),
    },
  ];
  const scopeNotes = [
    t('plugins.secrets.tips.scopeUser'),
    t('plugins.secrets.tips.scopeWorkspace'),
    t('plugins.secrets.tips.scopeOverride'),
  ];
  const safetyNotes = [
    t('plugins.secrets.tips.safetyMasked'),
    t('plugins.secrets.tips.safetyUninstall'),
    t('plugins.secrets.tips.safetyStudents'),
  ];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1 px-2 py-1.5 text-xs rounded-md transition-colors hover:bg-foreground/10"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          <Info className="h-3.5 w-3.5" />
          {t('plugins.secrets.tips.trigger')}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-80 max-h-[70vh] overflow-y-auto p-4"
        // Native focus lands on the trigger button; this is a reading panel.
        aria-label={t('plugins.secrets.tips.trigger')}
      >
        <div
          className="flex flex-col gap-3 text-xs leading-relaxed"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          <p>{t('plugins.secrets.tips.intro')}</p>

          <TipsSection title={t('plugins.secrets.tips.scenariosTitle')}>
            <ul className="flex flex-col gap-2">
              {scenarios.map((scenario) => (
                <li key={scenario.title}>
                  <span
                    className="font-medium"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {scenario.title}
                  </span>
                  <span> — {scenario.body}</span>
                </li>
              ))}
            </ul>
          </TipsSection>

          <TipsSection title={t('plugins.secrets.tips.scopesTitle')}>
            <ul className="flex flex-col gap-2">
              {scopeNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </TipsSection>

          <TipsSection title={t('plugins.secrets.tips.safetyTitle')}>
            <ul className="flex flex-col gap-2">
              {safetyNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </TipsSection>

          <p style={{ color: 'var(--color-text-tertiary)' }}>
            {t('plugins.secrets.tips.footer')}
          </p>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function TipsSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h4
        className="text-[0.6875rem] font-semibold uppercase tracking-wider"
        style={{ color: 'var(--color-text-tertiary)' }}
      >
        {title}
      </h4>
      {children}
    </section>
  );
}
