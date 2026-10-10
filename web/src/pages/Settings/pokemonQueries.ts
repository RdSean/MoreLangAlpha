import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { queryKeys } from '@/lib/queryKeys';
import { getPokemonCatalog, type PokemonCatalogParams } from './pokemonApi';

export function usePokemonCatalog(params: PokemonCatalogParams) {
  const { member } = useAuth();
  return useQuery({
    queryKey: queryKeys.education.pokemonCatalog(member?.user_id ?? '', params),
    queryFn: ({ signal }) => getPokemonCatalog(params, signal),
    enabled: member?.role === 'parent',
    staleTime: 5 * 60_000,
  });
}
