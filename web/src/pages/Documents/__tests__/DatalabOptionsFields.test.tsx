import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import DatalabOptionsFields from '../components/DatalabOptionsFields';
import MethodStep from '../components/steps/MethodStep';
import { toParserOptions, type DatalabOptions, type ParserOption } from '../types';

function parserOption(overrides: Partial<ParserOption> = {}): ParserOption {
  return {
    parser_id: 'datalab-online',
    display_name: 'Datalab (hosted)',
    version: null,
    supported_formats: ['pdf'],
    supported_classifications: ['scanned'],
    available: true,
    reason: 'Hosted conversion.',
    recommended: true,
    ...overrides,
  } as ParserOption;
}

/** The panel is controlled; the harness is the part that holds the state. */
function Harness() {
  const [value, setValue] = useState<DatalabOptions>({});
  return (
    <>
      <DatalabOptionsFields value={value} onChange={setValue} />
      <output data-testid="payload">{JSON.stringify(toParserOptions(value))}</output>
    </>
  );
}

describe('Datalab options panel', () => {
  it('starts with nothing set', () => {
    render(<Harness />);
    expect(screen.getByTestId('payload')).toHaveTextContent('{}');
  });

  it('sends only what the user changed', () => {
    render(<Harness />);

    fireEvent.change(screen.getByLabelText(/Processing mode|解析模式/i), {
      target: { value: 'accurate' },
    });

    // Not `{mode: 'accurate', paginate: true, disable_image_extraction: true}`:
    // the untouched fields stay absent so a later server-side default change is
    // not overridden by a wizard loaded before it.
    expect(screen.getByTestId('payload')).toHaveTextContent('{"mode":"accurate"}');
  });

  it('drops a field again when it returns to its default', () => {
    render(<Harness />);
    const select = screen.getByLabelText(/Processing mode|解析模式/i);

    fireEvent.change(select, { target: { value: 'accurate' } });
    fireEvent.change(select, { target: { value: 'balanced' } });

    expect(screen.getByTestId('payload')).toHaveTextContent('{}');
  });

  it('carries a page range through', () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText(/Page range|解析范围/i), {
      target: { value: '0-5,10' },
    });
    expect(screen.getByTestId('payload')).toHaveTextContent('{"page_range":"0-5,10"}');
  });

  it('omits undefined rather than sending nulls', () => {
    expect(toParserOptions({ mode: undefined, paginate: false })).toEqual({
      paginate: false,
    });
  });
});

describe('the wizard step', () => {
  function renderStep(selectedParserId: string) {
    return render(
      <MethodStep
        options={[
          parserOption(),
          parserOption({
            parser_id: 'anydoc-local',
            display_name: 'AnyDoc Local',
            recommended: false,
          }),
        ]}
        selectedParserId={selectedParserId}
        pending={false}
        datalabOptions={{}}
        onDatalabOptionsChange={() => {}}
        onSelect={() => {}}
        onBack={() => {}}
        onStart={() => {}}
      />,
    );
  }

  it('offers the panel for the hosted parser', () => {
    renderStep('datalab-online');
    expect(screen.getByTestId('datalab-options')).toBeInTheDocument();
  });

  it('hides the panel for a parser that takes no options', () => {
    // Showing empty controls for a local parser would suggest it can be tuned
    // when it cannot.
    renderStep('anydoc-local');
    expect(screen.queryByTestId('datalab-options')).not.toBeInTheDocument();
  });

  it('keeps the panel collapsed until asked', () => {
    renderStep('datalab-online');
    const panel = screen.getByTestId('datalab-options') as HTMLDetailsElement;
    expect(panel.open).toBe(false);
    // Collapsed must still mean present-and-findable for a screen reader.
    expect(within(panel).getByText(/Advanced options|高级选项/i)).toBeInTheDocument();
  });
});
