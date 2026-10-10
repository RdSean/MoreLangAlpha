import { useState } from 'react';
import { ImageOff, RotateCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { PokemonCard } from '@/pages/Settings/pokemonApi';

export default function PokemonCardImage({ card, url, eager = false }: { card: PokemonCard; url: string; eager?: boolean }) {
  const [failed, setFailed] = useState(false); const [attempt, setAttempt] = useState(0);
  return <div className="pokemon-card-image" style={{ aspectRatio: `${card.image_width} / ${card.image_height}` }}>
    {failed ? <div className="pokemon-image-error"><ImageOff size={24} aria-hidden="true" /><span>卡图暂不可用</span>
      <Button variant="ghost" size="icon" title="重新加载" aria-label={`重新加载${card.name}卡图`} onClick={() => { setAttempt(value => value + 1); setFailed(false); }}><RotateCw size={16} aria-hidden="true" /></Button></div>
      : <img src={attempt ? `${url}${url.includes('?') ? '&' : '?'}retry=${attempt}` : url} alt={`${card.name} · ${card.card_number}`} width={card.image_width} height={card.image_height} loading={eager ? 'eager' : 'lazy'} decoding="async" onError={() => setFailed(true)} />}
  </div>;
}
