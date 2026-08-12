import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import SourcesPanel from '../SourcesPanel';
import type { ProvenanceRecord } from '@/types/chat';

beforeAll(() => {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false;
    Element.prototype.setPointerCapture = () => {};
    Element.prototype.releasePointerCapture = () => {};
  }
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
});

function record(
  partial: Partial<ProvenanceRecord> & Pick<ProvenanceRecord, 'record_id' | 'source_type' | 'identifier'>,
): ProvenanceRecord {
  return { timestamp: '2026-01-01T00:00:00Z', ...partial } as ProvenanceRecord;
}

afterEach(() => vi.restoreAllMocks());

describe('SourcesPanel', () => {
  it('renders an empty state when there are no records', () => {
    render(<SourcesPanel provenanceRecords={{}} />);
    expect(screen.getByText('No sources for this turn')).toBeInTheDocument();
  });

  it('groups web search and MCP tool records', () => {
    render(<SourcesPanel provenanceRecords={{
      r1: record({ record_id: 'r1', source_type: 'web_search', identifier: 'https://example.com/a', title: 'Result A' }),
      r2: record({ record_id: 'r2', source_type: 'web_search', identifier: 'https://example.com/b', title: 'Result B' }),
      r3: record({ record_id: 'r3', source_type: 'mcp_tool', identifier: 'workspace-server:list_files', title: 'Workspace files' }),
    }} />);

    expect(screen.getByText('Web search')).toBeInTheDocument();
    expect(screen.getByTestId('group-count-web_search')).toHaveTextContent('2');
    expect(screen.getByTestId('group-count-mcp_tool')).toHaveTextContent('1');
  });

  it('deduplicates repeated web fetches by URL', () => {
    render(<SourcesPanel provenanceRecords={{
      r1: record({ record_id: 'r1', source_type: 'web_fetch', identifier: 'https://example.com/page', title: 'Page' }),
      r2: record({ record_id: 'r2', source_type: 'web_fetch', identifier: 'https://example.com/page', title: 'Page again' }),
    }} />);

    expect(screen.getAllByText('Page')).toHaveLength(1);
    expect(screen.queryByText('Page again')).not.toBeInTheDocument();
  });

  it('opens a URL in a new tab from the details dialog', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(<SourcesPanel provenanceRecords={{
      r1: record({ record_id: 'r1', source_type: 'web_search', identifier: 'https://example.com/a', title: 'Result A' }),
    }} />);

    fireEvent.click(screen.getByText('Result A'));
    fireEvent.click(screen.getByRole('button', { name: 'Open link' }));
    expect(openSpy).toHaveBeenCalledWith('https://example.com/a', '_blank', 'noopener,noreferrer');
  });

  it('routes file, memo, and memory records through onOpenFile', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    const onOpenFile = vi.fn();
    render(<SourcesPanel provenanceRecords={{
      r1: record({ record_id: 'r1', source_type: 'file_read', identifier: 'work/notes.md', title: 'notes.md' }),
      r2: record({ record_id: 'r2', source_type: 'memo_read', identifier: '.agents/user/memo/brief.md', title: 'brief.md' }),
      r3: record({ record_id: 'r3', source_type: 'memory_read', identifier: '.agents/user/memory/profile.md', title: 'profile.md' }),
    }} onOpenFile={onOpenFile} />);

    fireEvent.click(screen.getByText('notes.md'));
    fireEvent.click(screen.getByRole('button', { name: 'Open file' }));
    expect(onOpenFile).toHaveBeenCalledWith('work/notes.md');
    expect(openSpy).not.toHaveBeenCalled();
  });
});
