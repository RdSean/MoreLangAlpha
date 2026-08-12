/**
 * Shared provenance dedup helpers: provenanceDisplayKey and
 * countDedupedSources are the single source of truth used by both the Sources
 * pill (MessageList) and the Sources panel so their counts cannot diverge.
 * provenanceRecordKey is the storage key for the live/replay accumulator.
 */
import { describe, it, expect } from 'vitest';
import {
  provenanceMcpKey,
  provenanceDisplayKey,
  countDedupedSources,
  type ProvenanceRecord,
} from '../chat';
import { provenanceRecordKey } from '@/pages/ChatAgent/hooks/utils/streamEventHandlers';

function rec(
  source_type: string,
  identifier: string,
  args_fingerprint?: Record<string, unknown>,
  result_sha256?: string,
): ProvenanceRecord {
  return {
    record_id: `${source_type}:${identifier}:${JSON.stringify(args_fingerprint ?? null)}:${result_sha256 ?? ''}`,
    timestamp: '2026-01-01T00:00:00Z',
    source_type: source_type as ProvenanceRecord['source_type'],
    identifier,
    args_fingerprint,
    result_sha256,
  };
}

describe('provenanceMcpKey', () => {
  it('is empty for non-mcp_tool sources even with a fingerprint and sha', () => {
    expect(provenanceMcpKey(rec('web_search', 'https://x/a', { sha256: 'h' }, 'r'))).toBe('');
  });

  it('is empty for an mcp_tool call with neither args nor a result hash', () => {
    expect(provenanceMcpKey(rec('mcp_tool', 'srv:list_tools'))).toBe('');
  });

  it('includes the args fingerprint', () => {
    expect(provenanceMcpKey(rec('mcp_tool', 'docs:get_document', { sha256: 'abc' }))).toBe(
      '{"sha256":"abc"}#',
    );
  });

  it('includes the result hash, so same-args calls returning different data differ', () => {
    // A repeated query can return a different result; the result hash must
    // keep those accesses distinct.
    const a = provenanceMcpKey(
      rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a' }, 'r1'),
    );
    const b = provenanceMcpKey(
      rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a' }, 'r2'),
    );
    expect(a).not.toBe(b);
  });

  it('falls back to the args fingerprint when the result hash is nulled (oversized body)', () => {
    // Bodies over the inline cap have result_sha256 nulled server-side, so the
    // key can only lean on args. Same args still collapse; different args stay
    // distinct — truncation must not merge unrelated oversized calls.
    const same = provenanceMcpKey(rec('mcp_tool', 'srv:dump', { sha256: 'q' }, undefined));
    const sameAgain = provenanceMcpKey(rec('mcp_tool', 'srv:dump', { sha256: 'q' }, undefined));
    const other = provenanceMcpKey(rec('mcp_tool', 'srv:dump', { sha256: 'z' }, undefined));
    expect(same).toBe('{"sha256":"q"}#');
    expect(same).toBe(sameAgain);
    expect(same).not.toBe(other);
  });

  it('keys a no-arg tool purely by its result hash', () => {
    // A tool called with no arguments (e.g. a list/status call) has an empty
    // fingerprint, so the result hash is the only discriminator: same bytes
    // collapse, different bytes stay apart.
    const r1 = provenanceMcpKey(rec('mcp_tool', 'docs:list_resources', undefined, 'r1'));
    const r2 = provenanceMcpKey(rec('mcp_tool', 'docs:list_resources', undefined, 'r2'));
    expect(r1).toBe('#r1');
    expect(r1).not.toBe(r2);
  });
});

describe('provenanceDisplayKey', () => {
  it('keys on (source_type, identifier)', () => {
    expect(provenanceDisplayKey(rec('web_search', 'https://example.com/a'))).toBe(
      'web_search https://example.com/a',
    );
  });

  it('tolerates missing fields without throwing', () => {
    expect(provenanceDisplayKey({} as ProvenanceRecord)).toBe(' ');
  });

  it('separates two calls to one mcp_tool by args', () => {
    // Both share an identifier — only args differ. The
    // key must distinguish them or the second call overwrites the first.
    const chapterA = provenanceDisplayKey(
      rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a' }),
    );
    const chapterB = provenanceDisplayKey(
      rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-b' }),
    );
    expect(chapterA).not.toBe(chapterB);
  });
});

describe('countDedupedSources', () => {
  it('returns 0 for null/undefined', () => {
    expect(countDedupedSources(undefined)).toBe(0);
    expect(countDedupedSources(null)).toBe(0);
  });

  it('collapses same web URL to one — ignoring distinct shas (collapse-by-URL)', () => {
    const records = {
      a: { ...rec('web_fetch', 'https://example.com/p'), result_sha256: 'sha-1' },
      b: { ...rec('web_fetch', 'https://example.com/p'), result_sha256: 'sha-2' },
      c: rec('mcp_tool', 'docs:list_resources'),
    };
    // Two distinct display keys: the duplicated URL collapses despite differing
    // shas (web sources intentionally omit sha from the key). mcp_tool keeps sha
    // (see below), but here docs:list_resources has no args/sha so it is its own row.
    expect(countDedupedSources(records)).toBe(2);
  });

  it('matches the panel grouping logic for distinct identifiers', () => {
    const records = {
      a: rec('web_search', 'https://example.com/a'),
      b: rec('web_search', 'https://example.com/b'),
    };
    expect(countDedupedSources(records)).toBe(2);
  });

  it('counts two same-tool mcp calls with different args as two sources', () => {
    // Two document reads in one
    // execute_code/bash block share source_type + identifier; only the args
    // fingerprint differs. Both must be counted.
    const records = {
      a: rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a' }),
      b: rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-b' }),
    };
    expect(countDedupedSources(records)).toBe(2);
  });

  it('counts same-tool calls with different arguments as two sources', () => {
    // The fingerprint is over the whole argument set, so different document
    // sections remain distinct sources.
    const records = {
      first: rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a-intro' }),
      second: rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a-notes' }),
    };
    expect(countDedupedSources(records)).toBe(2);
  });

  it('counts same-args mcp calls that returned different data as two sources', () => {
    // Identical arguments can still produce different results. Neither access
    // may be silently overwritten.
    const records = {
      first: rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a' }, 'revision-1'),
      second: rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a' }, 'revision-2'),
    };
    expect(countDedupedSources(records)).toBe(2);
  });

  it('collapses a true duplicate (same args AND same result) to one source', () => {
    // A re-delivered/replayed event for the same access — identical args AND
    // identical result hash — is one source, not two.
    const records = {
      a: rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a' }, 'same-bytes'),
      b: rec('mcp_tool', 'docs:get_document', { sha256: 'chapter-a' }, 'same-bytes'),
    };
    expect(countDedupedSources(records)).toBe(1);
  });

  it('shows one card for the same data product fetched in two code blocks', () => {
    // The live storage key includes tool_call_id (so both events are retained),
    // but the display key omits it — identical identifier+args+result collapse to
    // one card. The same statement read in two execute_code blocks shows once.
    const records = {
      a: rec('mcp_tool', 'docs:get_outline', { sha256: 'guide' }, 'bytes'),
      b: rec('mcp_tool', 'docs:get_outline', { sha256: 'guide' }, 'bytes'),
    };
    expect(countDedupedSources(records)).toBe(1);
  });

  it('counts a no-arg mcp tool by its result hash', () => {
    const distinct = {
      a: rec('mcp_tool', 'docs:list_resources', undefined, 'r1'),
      b: rec('mcp_tool', 'docs:list_resources', undefined, 'r2'),
    };
    const same = {
      a: rec('mcp_tool', 'docs:list_resources', undefined, 'r1'),
      b: rec('mcp_tool', 'docs:list_resources', undefined, 'r1'),
    };
    expect(countDedupedSources(distinct)).toBe(2);
    expect(countDedupedSources(same)).toBe(1);
  });
});

describe('provenanceRecordKey', () => {
  it('is unchanged for non-mcp_tool sources (no discriminator suffix)', () => {
    expect(
      provenanceRecordKey({
        tool_call_id: 'call-1',
        source_type: 'web_search',
        identifier: 'https://example.com/a',
        args_fingerprint: { sha256: 'h' },
        result_sha256: 'r',
      }),
    ).toBe('call-1:web_search:https://example.com/a');
  });

  it('keeps two same-tool mcp calls distinct despite a shared tool_call_id', () => {
    // The root-cause case: both in-sandbox MCP calls inherit the outer
    // execute_code/bash tool_call_id AND the same "server:tool" identifier, so
    // the discriminator is the only thing keeping them from colliding.
    const chapterA = provenanceRecordKey({
      tool_call_id: 'bash-1',
      source_type: 'mcp_tool',
      identifier: 'docs:get_document',
      args_fingerprint: { sha256: 'chapter-a' },
    });
    const chapterB = provenanceRecordKey({
      tool_call_id: 'bash-1',
      source_type: 'mcp_tool',
      identifier: 'docs:get_document',
      args_fingerprint: { sha256: 'chapter-b' },
    });
    expect(chapterA).not.toBe(chapterB);
  });

  it('keeps same-args calls distinct when the result differs (time-varying data)', () => {
    const first = provenanceRecordKey({
      tool_call_id: 'bash-1',
      source_type: 'mcp_tool',
      identifier: 'docs:get_document',
      args_fingerprint: { sha256: 'chapter-a' },
      result_sha256: 'revision-1',
    });
    const second = provenanceRecordKey({
      tool_call_id: 'bash-1',
      source_type: 'mcp_tool',
      identifier: 'docs:get_document',
      args_fingerprint: { sha256: 'chapter-a' },
      result_sha256: 'revision-2',
    });
    expect(first).not.toBe(second);
  });

  it('collapses a byte-identical duplicate within one code block to one storage key', () => {
    // Same tool_call_id, identifier, args AND result (a re-emitted access, or
    // the agent calling an identical historical query twice in one block): the
    // accumulator stores it once rather than as two look-alike cards.
    const call = {
      tool_call_id: 'bash-1',
      source_type: 'mcp_tool',
      identifier: 'docs:get_document',
      args_fingerprint: { sha256: 'chapter-a' },
      result_sha256: 'bytes',
    };
    expect(provenanceRecordKey(call)).toBe(provenanceRecordKey({ ...call }));
  });

  it('keeps the same access in two different code blocks under separate keys', () => {
    // Distinct execute_code blocks carry distinct tool_call_ids, which the
    // storage key includes — so both live events survive (the display key later
    // collapses them; see countDedupedSources). This divergence is intentional.
    const common = {
      source_type: 'mcp_tool' as const,
      identifier: 'docs:get_document',
      args_fingerprint: { sha256: 'chapter-a' },
      result_sha256: 'bytes',
    };
    expect(provenanceRecordKey({ ...common, tool_call_id: 'bash-1' })).not.toBe(
      provenanceRecordKey({ ...common, tool_call_id: 'bash-2' }),
    );
  });

});
