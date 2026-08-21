import type { FamilyLlmAvailability } from '@/pages/Settings/api';
import type { FamilyModelOption } from '@/components/ui/chat-input.types';

export interface FamilyModelAvailabilityState {
  initialModel: string | null;
  models: FamilyModelOption[];
  status: 'loading' | 'ready' | 'empty' | 'error';
}

/** Projects the server-owned household model state for the student composer. */
export function buildFamilyModelAvailability(
  availability: FamilyLlmAvailability | null | undefined,
  isLoading: boolean,
  isError: boolean,
): FamilyModelAvailabilityState {
  if (isError) {
    return { initialModel: null, models: [], status: 'error' };
  }

  const models = availability?.models ?? [];
  const selectedModel = models.find(
    (model) => model.model_key === availability?.selected_model_key,
  ) ?? null;

  return {
    initialModel: selectedModel?.model_key ?? null,
    models: models.map((model) => ({
      modelKey: model.model_key,
      displayName: model.display_name,
    })),
    status: isLoading ? 'loading' : models.length > 0 ? 'ready' : 'empty',
  };
}
