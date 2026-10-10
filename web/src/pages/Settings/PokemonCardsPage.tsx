import { useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ChevronLeft, ChevronRight, RotateCw } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { pokemonCardImageUrl, type PokemonCard } from './pokemonApi';
import { usePokemonCatalog } from './pokemonQueries';
import PokemonCardImage from '@/components/education/PokemonCardImage';
import './PokemonCardsPage.css';

function CardImage({ card, eager = false }: { card: PokemonCard; eager?: boolean }) {
  return <PokemonCardImage card={card} url={pokemonCardImageUrl(card.card_id)} eager={eager} />;
}

export default function PokemonCardsPage() {
  const { member } = useAuth();
  const [params, setParams] = useSearchParams();
  const requestedPage = Number(params.get('page') ?? 1);
  const page = Number.isInteger(requestedPage) && requestedPage >= 1 && requestedPage <= 10000 ? requestedPage : 1;
  const setCode = params.get('series') || undefined;
  const catalog = usePokemonCatalog({ page, page_size: 20, set_code: setCode });
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const totalPages = Math.max(1, Math.ceil((catalog.data?.total ?? 0) / 20));
  const currentPage = catalog.data?.page ?? page;
  const changePage = (nextPage: number, nextSet = setCode) => {
    setParams({ ...(nextSet ? { series: nextSet } : {}), ...(nextPage > 1 ? { page: String(nextPage) } : {}) });
    pageRef.current?.scrollTo?.({ top: 0, behavior: 'instant' });
  };

  return <div className="pokemon-catalog-page" ref={pageRef}>
    <div className="pokemon-catalog-container">
      <Link to="/settings?tab=family" className="pokemon-catalog-back"><ArrowLeft size={16} aria-hidden="true" />家庭账户</Link>
      <header className="pokemon-catalog-header">
        <div><h1>宝可梦卡牌</h1><p aria-live="polite">{catalog.data ? `共 ${catalog.data.total} 张卡牌` : '卡牌目录'}</p></div>
        {member?.role === 'parent' && <select className="pokemon-catalog-select" aria-label="卡牌系列" value={setCode ?? ''} onChange={event => changePage(1, event.target.value)} disabled={catalog.isLoading}>
          <option value="">全部系列</option>
          {(catalog.data?.series ?? []).map(series => <option key={series.set_code} value={series.set_code}>{series.series_name} · {series.total}</option>)}
        </select>}
      </header>
      {member?.role !== 'parent' ? <p className="pokemon-catalog-state">只有家长可以查看卡牌目录。</p> : <>
        {catalog.isLoading && <div role="status" aria-label="正在加载卡牌" className="pokemon-catalog-grid">{Array.from({ length: 20 }, (_, index) => <div key={index} className="pokemon-card-skeleton" />)}</div>}
        {catalog.isError && <div className="pokemon-catalog-state"><p role="alert">无法加载卡牌目录。</p><Button variant="outline" onClick={() => void catalog.refetch()}><RotateCw size={16} className="mr-2" aria-hidden="true" />重试</Button></div>}
        {catalog.data && !catalog.isError && <>
          {catalog.data.items.length === 0 ? <p className="pokemon-catalog-state">暂无卡牌</p> : <div className="pokemon-catalog-grid" aria-label="卡牌目录">
            {catalog.data.items.map(card => <article key={card.card_id} className="pokemon-catalog-card">
              <button type="button" className="pokemon-card-open" aria-label={`查看${card.name} · ${card.card_number}`} onClick={() => setSelectedCard(card)}><span className="sr-only">{card.name}</span></button>
              <CardImage card={card} />
              <div className="pokemon-card-caption"><h2>{card.name}</h2><p>{card.series_name}</p><div><span>{card.card_number}</span><span>{card.rarity || card.category}</span></div></div>
            </article>)}
          </div>}
        </>}
        <nav className="pokemon-catalog-pagination" aria-label="卡牌分页">
          <Button size="icon" variant="outline" aria-label="上一页" title="上一页" disabled={!catalog.data || catalog.isError || currentPage <= 1 || catalog.isFetching} onClick={() => changePage(currentPage - 1)}><ChevronLeft size={18} aria-hidden="true" /></Button>
          <label className="pokemon-page-label"><span className="sr-only">页码</span><select className="pokemon-catalog-select" value={Math.min(currentPage, totalPages)} disabled={!catalog.data || catalog.isError || catalog.isFetching} onChange={event => changePage(Number(event.target.value))}>{Array.from({ length: totalPages }, (_, index) => <option value={index + 1} key={index}>{index + 1}</option>)}</select><span>/ {totalPages} 页</span></label>
          <Button size="icon" variant="outline" aria-label="下一页" title="下一页" disabled={!catalog.data || catalog.isError || currentPage >= totalPages || catalog.isFetching} onClick={() => changePage(currentPage + 1)}><ChevronRight size={18} aria-hidden="true" /></Button>
        </nav>
      </>}
      <Dialog open={Boolean(selectedCard)} onOpenChange={open => { if (!open) setSelectedCard(null); }}>
        <DialogContent variant="centered" className="pokemon-detail-dialog">
          {selectedCard && <><DialogHeader><DialogTitle>{selectedCard.name}</DialogTitle><DialogDescription>{selectedCard.series_name} · {selectedCard.card_number}</DialogDescription></DialogHeader>
            <div className="pokemon-detail-content"><CardImage key={selectedCard.card_id} card={selectedCard} eager /><dl className="pokemon-detail-metadata">
              {Object.entries({ 类别: selectedCard.category, 属性: selectedCard.element, HP: selectedCard.hp, 阶段: selectedCard.stage, 稀有度: selectedCard.rarity, 画师: selectedCard.illustrator, 备注: selectedCard.notes }).filter(([, value]) => value !== null && value !== '').map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
            </dl></div></>}
        </DialogContent>
      </Dialog>
    </div>
  </div>;
}
