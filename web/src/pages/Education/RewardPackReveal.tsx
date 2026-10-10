import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import PokemonCardImage from '@/components/education/PokemonCardImage';
import type { PokemonCard } from '@/pages/Settings/pokemonApi';
import { rewardCardImageUrl, type OpenedRewardPack, type RewardSettings } from './rewardsApi';

export default function RewardPackReveal({ card, result, studentId, settings, onClose }: {
  card: PokemonCard | null; result?: OpenedRewardPack | null; studentId: string;
  settings?: RewardSettings; onClose: () => void;
}) {
  return <Dialog open={Boolean(card)} onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent variant="centered" className="pokemon-detail-dialog reward-detail-dialog">
      {card && <><DialogHeader><DialogTitle>{result ? result.owned_before ? '再次遇见' : '新卡加入收藏' : card.name}</DialogTitle>
        <DialogDescription>{card.series_name} · {card.card_number}</DialogDescription></DialogHeader>
        <div className="pokemon-detail-content"><PokemonCardImage key={`${studentId}/${card.card_id}`} card={card} url={rewardCardImageUrl(card.card_id, studentId)} eager />
          <div><h2>{card.name}</h2><dl className="pokemon-detail-metadata">
            {Object.entries({ 稀有度: card.rarity, 等级: result?.reward_level ? settings?.level_names[result.reward_level] : null, 属性: card.element, HP: card.hp, 阶段: card.stage, 画师: card.illustrator, 备注: card.notes }).filter(([, value]) => value !== null && value !== undefined && value !== '').map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
          </dl>{result && <p className="reward-result">{result.owned_before ? `收藏数量 ${result.owned_before + 1} 张` : '首次获得'}{result.returned_points > 0 ? ` · 返还 ${result.returned_points} 分` : ''}</p>}</div>
        </div><Button onClick={onClose}>{result ? '收下卡牌' : '关闭'}</Button></>}
    </DialogContent>
  </Dialog>;
}
