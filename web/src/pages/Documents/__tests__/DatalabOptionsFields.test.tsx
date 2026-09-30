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
    expect(screen.getByRole('checkbox', { name: /Add page markers|添加分页标记/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Keep page header|保留页眉/i })).toBeChecked();
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

  it('treats the image switch as extract, not as the wire flag', () => {
    render(<Harness />);
    const toggle = screen.getByLabelText(
      /Extract images|提取图片/i,
    ) as HTMLInputElement;

    // Images are extracted by default now that they are published and shown.
    // The checkbox is still the positive reading of a negative field: ticked
    // means extract, and only switching it *off* has anything to send.
    expect(toggle).toBeChecked();
    expect(screen.getByTestId('payload')).toHaveTextContent('{}');

    fireEvent.click(toggle);
    expect(screen.getByTestId('payload')).toHaveTextContent(
      '{"disable_image_extraction":true}',
    );

    fireEvent.click(toggle);
    expect(screen.getByTestId('payload')).toHaveTextContent('{}');
  });

  it('splits the panel into two rows of one kind of control', () => {
    // The panel used to be a single ragged column of five mixed controls —
    // checkbox, checkbox, select, text, checkbox — which is what made it look
    // unstyled. Row one takes values, row two is switches, and neither row
    // mixes the two.
    render(<Harness />);
    const fields = screen.getByTestId('datalab-options-fields');
    const toggles = screen.getByTestId('datalab-options-toggles');

    expect(
      within(fields).getByLabelText(/Processing mode|解析模式/i),
    ).toBeInTheDocument();
    expect(within(fields).getByLabelText(/Page range|解析范围/i)).toBeInTheDocument();
    expect(within(fields).queryAllByRole('checkbox')).toHaveLength(0);

    expect(within(toggles).getAllByRole('checkbox')).toHaveLength(10);
    expect(within(toggles).queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('ships image captions off, and only sends the flag when switched on', () => {
    render(<Harness />);
    // By role: the tip button beside this switch borrows the label as the
    // start of its own accessible name, so a text query matches two elements.
    const toggle = screen.getByRole('checkbox', {
      name: /Skip image captions|不生成图片标题/i,
    }) as HTMLInputElement;

    // Datalab generates captions by default and they can pull accuracy away
    // from the surrounding text, so our default is the opposite of theirs —
    // and the label is negative so a ticked box means what it says.
    expect(toggle).toBeChecked();
    expect(screen.getByTestId('payload')).toHaveTextContent('{}');

    fireEvent.click(toggle);
    expect(screen.getByTestId('payload')).toHaveTextContent(
      '{"disable_image_captions":false}',
    );
  });

  it('explains the caption default in a tip beside the switch', () => {
    render(<Harness />);
    const tip = screen.getByRole('button', {
      name: /Skip image captions|不生成图片标题/i,
    });

    // The reason matters more than the flag: without it, "skip captions"
    // reads like a lost feature rather than a deliberate default.
    expect(tip).toHaveAccessibleName(/accuracy|精度/i);
  });

  it('sends structure and content feature toggles using their Datalab wire fields', () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole('checkbox', { name: /Merge cross-page|合并跨页/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Keep page footer|保留页脚/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Extract links|提取链接/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /New block types|新的块类型/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /Add block IDs|添加块 ID/i }));

    expect(screen.getByTestId('payload')).toHaveTextContent(
      '{"merge_cross_page":true,"keep_pagefooter_in_output":true,"extract_links":true,"new_block_types":true,"add_block_ids":true}',
    );
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
