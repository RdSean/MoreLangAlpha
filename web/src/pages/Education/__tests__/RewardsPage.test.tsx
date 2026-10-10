import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AxiosError } from 'axios';
import RewardsPage from '../RewardsPage';
import * as api from '../rewardsApi';

const state = vi.hoisted(() => ({ role: 'student' as 'student' | 'parent' }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ member: { user_id: state.role === 'student' ? 'child' : 'parent', household_id: 'family', role: state.role } }) }));
vi.mock('../queries', () => ({ useEducationMembers: () => ({ data: [{ user_id: 'child', name: '孩子', role: 'student' }], isLoading: false }), useEducationHomeworkDictionaries: () => ({ data: { timezone: 'UTC' } }) }));
const probabilities = { basic: .85, rare: .15, featured: 0, premium: 0, legendary: 0 };
const settings: api.RewardSettings = { prices: { daily: 5, featured: 15, rare: 30 }, pack_names: { daily: '日常包', featured: '精选包', rare: '稀有包' }, level_names: { basic: '基础', rare: '稀有', featured: '精选', premium: '高级', legendary: '传说' }, probabilities: { daily: probabilities, featured: probabilities, rare: probabilities }, effective_probabilities: { daily: probabilities, featured: probabilities, rare: probabilities }, updated_at: null };
const pack: api.RewardPack = { pack_id: 'pack', source: 'purchase', pack_type: 'daily', reward_date: '2026-10-11', streak_node: null, price: 5, probabilities, policy_version: 'v1', card_id: null, reward_level: null, owned_before: null, returned_points: 0, effective_probabilities: null, created_at: '2026-10-11T00:00:00Z', opened_at: null };

beforeEach(() => {
  vi.restoreAllMocks(); localStorage.clear(); state.role = 'student';
  vi.spyOn(api, 'syncRewards').mockResolvedValue({ student_id: 'child', balance: 50, homework_points: 50, streak: 3, next_streak_node: 5, unopened_count: 1, today_rewarded: true, settled_through: '2026-10-10' });
  vi.spyOn(api, 'getRewardSettings').mockResolvedValue(settings);
  vi.spyOn(api, 'getRewardPacks').mockResolvedValue({ items: [pack], total: 1, page: 1, page_size: 20 });
  vi.spyOn(api, 'getRewardCollection').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, series: [] });
  vi.spyOn(api, 'getRewardTransactions').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
});
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={client}><RewardsPage /></QueryClientProvider></MemoryRouter>);
}
describe('learning rewards', () => {
  it('recovers the same purchase after network uncertainty', async () => {
    const purchase = vi.spyOn(api, 'purchaseReward').mockRejectedValueOnce(new AxiosError('network')).mockResolvedValueOnce(pack);
    mount(); fireEvent.click(await screen.findByRole('button', { name: '积分兑换' }));
    fireEvent.click(await screen.findByRole('button', { name: '兑换日常包' }));
    fireEvent.click(screen.getByRole('button', { name: '确认兑换' }));
    await waitFor(() => expect(purchase).toHaveBeenCalledTimes(1));
    fireEvent.click(await screen.findByRole('button', { name: '重试原兑换' }));
    await waitFor(() => expect(purchase).toHaveBeenCalledTimes(2));
    expect(purchase.mock.calls[0][0]).toEqual(purchase.mock.calls[1][0]);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(localStorage.length).toBe(0);
  });
  it('parents can inspect rewards but cannot spend or open', async () => {
    state.role = 'parent'; mount();
    await screen.findByText('日常包'); expect(screen.queryByRole('button', { name: '打开卡包' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '积分兑换' }));
    await screen.findByText('精选包'); expect(screen.queryByRole('button', { name: '兑换日常包' })).not.toBeInTheDocument();
  });
});
