import { describe, expect, expectTypeOf, it } from 'vitest';
import type {
  BookAttemptTiming, BookExecutionPhase, BookPreparationProgress,
  CreateManagedTextbookResponse, FrozenBookSource, TextbookWorkbench,
} from '../types';

describe('processing API contracts', () => {
  it('separates selected metadata from a nullable frozen source', () => {
    expectTypeOf<TextbookWorkbench['source']>().toEqualTypeOf<FrozenBookSource | null>();
    expectTypeOf<TextbookWorkbench['source_status']>().toEqualTypeOf<
      'pending' | 'preparing' | 'ready' | 'failed' | 'cancelled'
    >();
    expectTypeOf<FrozenBookSource['frozen_at']>().toEqualTypeOf<string | null>();
  });

  it('distinguishes reused acceptance and preserves unknown timing', () => {
    expectTypeOf<CreateManagedTextbookResponse['acceptance']>().toEqualTypeOf<'accepted_new' | 'reused'>();
    const timing: BookAttemptTiming = {
      attempt: 1, request_round: 2, status: 'unavailable', queued_at: null,
      claimed_at: null, terminal_at: null, total_ms: null, phases: [],
    };
    expect(timing.total_ms).toBeNull();
    expectTypeOf<BookAttemptTiming['total_ms']>().toEqualTypeOf<number | null>();
  });

  it('uses resource progress separately from material success counts', () => {
    const progress: BookPreparationProgress = { total_resources: 129, verified_resources: 129 };
    expect(progress).not.toHaveProperty('succeeded_items');
    expectTypeOf<BookExecutionPhase>().toEqualTypeOf<
      'initial_queue' | 'source_freezing' | 'runtime_queue' | 'sandbox_preparation'
      | 'input_staging' | 'ptc_execution' | 'finalization'
    >();
  });
});
