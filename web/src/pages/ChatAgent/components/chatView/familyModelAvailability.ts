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

  const endpoints = availability?.endpoints ?? [];
  const selectedEndpoint = endpoints.find(
    (endpoint) => endpoint.endpoint_id === availability?.selected_endpoint_id,
  ) ?? null;

  return {
    initialModel: selectedEndpoint?.model_key ?? null,
    models: endpoints.map((endpoint) => ({
      modelKey: endpoint.model_key,
      displayName: endpoint.display_name,
    })),
    status: isLoading ? 'loading' : endpoints.length > 0 ? 'ready' : 'empty',
  };
}
