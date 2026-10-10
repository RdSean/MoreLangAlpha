import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PokemonCardsPage from '../PokemonCardsPage';

const state = vi.hoisted(() => ({ role: 'parent', getCatalog: vi.fn() }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ member: { user_id: 'parent-1', role: state.role } }) }));
vi.mock('../pokemonApi', () => ({
  getPokemonCatalog: state.getCatalog,
  pokemonCardImageUrl: (id: string) => `/api/v1/education/pokemon-cards/${id}/image`,
}));

const card = { card_id: 'card-1', source_card_id: 'me55-1', set_code: 'me55', series_name: '30周年庆典', name: '皮卡丘', category: '宝可梦', element: '雷', hp: 60, stage: '基础', card_number: '001', rarity: '稀有', illustrator: 'Artist', notes: '', image_width: 640, image_height: 880 };
const series = [{ set_code: 'me55', series_name: '30周年庆典', total: 21 }];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={client}><PokemonCardsPage /></QueryClientProvider></MemoryRouter>);
}

beforeEach(() => {
  state.role = 'parent';
  state.getCatalog.mockReset().mockImplementation(async (params: { page: number }) => ({
    items: [{ ...card, card_id: `card-${params.page}`, name: params.page === 1 ? '皮卡丘' : '伊布' }], total: 21, page: params.page, page_size: 20, series,
  }));
});

describe('PokemonCardsPage', () => {
  it('paginates and resets the page when selecting a series', async () => {
    renderPage();
    await screen.findByRole('button', { name: '查看皮卡丘 · 001' });
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    await screen.findByRole('button', { name: '查看伊布 · 001' });
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('卡牌系列'), { target: { value: 'me55' } });
    await waitFor(() => expect(state.getCatalog).toHaveBeenLastCalledWith({ page: 1, page_size: 20, set_code: 'me55' }, expect.anything()));
    fireEvent.change(screen.getByLabelText('卡牌系列'), { target: { value: '' } });
    await waitFor(() => expect(screen.getByLabelText('卡牌系列')).toHaveValue(''));
  });

  it('opens a complete card image and metadata in a dialog', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: '查看皮卡丘 · 001' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('画师Artist');
    expect(screen.getAllByAltText('皮卡丘 · 001')[1]).toHaveAttribute('src', '/api/v1/education/pokemon-cards/card-1/image');
  });

  it('does not request the parent catalog for a student', () => {
    state.role = 'student';
    renderPage();
    expect(screen.getByText('只有家长可以查看卡牌目录。')).toBeInTheDocument();
    expect(state.getCatalog).not.toHaveBeenCalled();
  });

  it('provides retry on failure and an empty state', async () => {
    state.getCatalog.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, series: [] });
    renderPage();
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    await screen.findByText('暂无卡牌');
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();
  });

  it('offers a retry when a card image cannot load', async () => {
    renderPage();
    const image = await screen.findByAltText('皮卡丘 · 001');
    fireEvent.error(image);
    fireEvent.click(screen.getByRole('button', { name: '重新加载皮卡丘卡图' }));
    expect(screen.getByAltText('皮卡丘 · 001')).toHaveAttribute('src', '/api/v1/education/pokemon-cards/card-1/image?retry=1');
  });
});
