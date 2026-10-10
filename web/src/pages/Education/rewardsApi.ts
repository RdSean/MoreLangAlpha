import { api } from '@/api/client';
import { isAxiosError } from 'axios';
import type { PokemonCard } from '@/pages/Settings/pokemonApi';

export type PackType = 'daily' | 'featured' | 'rare';
export type RewardLevel = 'basic' | 'rare' | 'featured' | 'premium' | 'legendary';
export interface RewardSummary {
  student_id: string; balance: number; homework_points: number; streak: number;
  next_streak_node: number; unopened_count: number; today_rewarded: boolean; settled_through: string | null;
}
export interface RewardPack {
  pack_id: string; source: 'daily' | 'streak' | 'purchase'; pack_type: PackType; reward_date: string;
  streak_node: number | null; price: number | null; probabilities: Record<RewardLevel, number>;
  policy_version: string; card_id: string | null; reward_level: RewardLevel | null; owned_before: number | null;
  returned_points: number; effective_probabilities: Record<RewardLevel, number> | null;
  created_at: string; opened_at: string | null;
}
export interface OpenedRewardPack extends RewardPack { card: PokemonCard }
export interface CollectionCard extends PokemonCard { quantity: number; reward_level: RewardLevel }
export interface RewardTransaction {
  entry_id: string; kind: 'homework' | 'purchase' | 'duplicate'; amount: number;
  task_id: string | null; task_title: string | null; pack_id: string | null; pack_type: PackType | null; created_at: string;
}
export interface RewardPage<T> { items: T[]; total: number; page: number; page_size: number; series?: { set_code: string; series_name: string }[] }
export interface RewardSettings {
  prices: Record<PackType, number>; probabilities: Record<PackType, Record<RewardLevel, number>>;
  pack_names: Record<PackType, string>; level_names: Record<RewardLevel, string>; updated_at: string | null;
  effective_probabilities: Record<PackType, Record<RewardLevel, number>>;
}
export interface PurchaseRequest { pack_type: PackType; expected_price: number; idempotency_key: string }
export interface RewardRecordParams { page: number; page_size: number; unopened?: boolean; level?: RewardLevel; set_code?: string }

const root = '/api/v1/education/rewards';
export function rewardError(error: unknown) {
  return isAxiosError<{ detail?: string }>(error) && typeof error.response?.data?.detail === 'string' ? error.response.data.detail : '连接暂时中断，请重试。';
}
export const rewardCardImageUrl = (id: string, studentId: string) => api.getUri({ url: `${root}/cards/${encodeURIComponent(id)}/image`, params: { student_id: studentId } });
export async function syncRewards(studentId: string) {
  return (await api.post<RewardSummary>(`${root}/sync`, null, { params: { student_id: studentId } })).data;
}
export async function getRewardPacks(studentId: string, params: RewardRecordParams, signal?: AbortSignal) {
  return (await api.get<RewardPage<RewardPack>>(`${root}/packs`, { params: { student_id: studentId, ...params }, signal })).data;
}
export async function getRewardCollection(studentId: string, params: RewardRecordParams, signal?: AbortSignal) {
  return (await api.get<RewardPage<CollectionCard>>(`${root}/collection`, { params: { student_id: studentId, ...params }, signal })).data;
}
export async function getRewardTransactions(studentId: string, params: RewardRecordParams, signal?: AbortSignal) {
  return (await api.get<RewardPage<RewardTransaction>>(`${root}/transactions`, { params: { student_id: studentId, ...params }, signal })).data;
}
export async function getRewardSettings() { return (await api.get<RewardSettings>(`${root}/settings`)).data; }
export async function purchaseReward(input: PurchaseRequest) { return (await api.post<RewardPack>(`${root}/purchases`, input)).data; }
export async function openRewardPack(packId: string) { return (await api.post<OpenedRewardPack>(`${root}/packs/${packId}/open`)).data; }
export async function updateRewardSettings(prices: Record<PackType, number>) { return (await api.put<RewardSettings>(`${root}/settings`, prices)).data; }
