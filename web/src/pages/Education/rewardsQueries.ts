import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { useAuth } from '@/contexts/AuthContext';
import * as api from './rewardsApi';

function useRewardScope(studentId: string) {
  const { member } = useAuth();
  return { viewer: `${member?.household_id ?? ''}/${member?.user_id ?? ''}`, student: studentId };
}
export function useRewardSync(studentId: string, today: string) {
  const scope = useRewardScope(studentId);
  const client = useQueryClient();
  return useQuery({
    queryKey: queryKeys.education.rewardSummary(scope, today),
    queryFn: async () => {
      const result = await api.syncRewards(studentId);
      await Promise.all(['packs', 'collection', 'transactions'].map(kind => client.invalidateQueries({ queryKey: queryKeys.education.rewardRecords(scope, kind) })));
      return result;
    }, enabled: Boolean(studentId && today),
    staleTime: 30_000, retry: 1,
  });
}
export function useRewardRecords<K extends 'packs' | 'collection' | 'transactions'>(studentId: string, kind: K, params: api.RewardRecordParams, enabled: boolean) {
  const scope = useRewardScope(studentId);
  type Item = K extends 'packs' ? api.RewardPack : K extends 'collection' ? api.CollectionCard : api.RewardTransaction;
  return useQuery<api.RewardPage<Item>>({
    queryKey: queryKeys.education.rewardRecords(scope, kind, params),
    queryFn: ({ signal }) => (kind === 'packs' ? api.getRewardPacks(studentId, params, signal)
      : kind === 'collection' ? api.getRewardCollection(studentId, params, signal) : api.getRewardTransactions(studentId, params, signal)) as Promise<api.RewardPage<Item>>,
    enabled: Boolean(studentId) && enabled, staleTime: 5_000,
  });
}
export function useRewardActions(studentId: string) {
  const client = useQueryClient(); const scope = useRewardScope(studentId);
  const invalidate = () => client.invalidateQueries({ queryKey: queryKeys.education.rewards(scope) });
  const purchase = useMutation({ mutationFn: api.purchaseReward, retry: false, onSuccess: invalidate });
  const open = useMutation({ mutationFn: api.openRewardPack, retry: false, onSuccess: invalidate });
  return { purchase, open };
}
export function useRewardSettings() {
  const { member } = useAuth(); const client = useQueryClient();
  const key = queryKeys.education.rewardSettings(`${member?.household_id ?? ''}/${member?.user_id ?? ''}`);
  const query = useQuery({ queryKey: key, queryFn: api.getRewardSettings, enabled: Boolean(member), staleTime: 30_000 });
  const save = useMutation({ mutationFn: api.updateRewardSettings, onSuccess: () => client.invalidateQueries({ queryKey: key }) });
  return { query, save };
}
