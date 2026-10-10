import { api } from '@/api/client';

export interface PokemonCard {
  card_id: string;
  source_card_id: string;
  set_code: string;
  series_name: string;
  name: string;
  category: string;
  element: string;
  hp: number | null;
  stage: string;
  card_number: string;
  rarity: string;
  illustrator: string;
  notes: string;
  image_width: number;
  image_height: number;
}

export interface PokemonCatalogParams {
  page: number;
  page_size: number;
  set_code?: string;
}

export interface PokemonCatalog {
  items: PokemonCard[];
  total: number;
  page: number;
  page_size: number;
  series: { set_code: string; series_name: string; total: number }[];
}

export async function getPokemonCatalog(params: PokemonCatalogParams, signal?: AbortSignal): Promise<PokemonCatalog> {
  return (await api.get<PokemonCatalog>('/api/v1/education/pokemon-cards', { params, signal })).data;
}

export function pokemonCardImageUrl(cardId: string): string {
  return api.getUri({ url: `/api/v1/education/pokemon-cards/${encodeURIComponent(cardId)}/image` });
}
