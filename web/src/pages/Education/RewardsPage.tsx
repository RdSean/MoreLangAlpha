import { useEffect, useRef, useState } from 'react';
import { isAxiosError } from 'axios';
import { ArrowLeft, ChevronLeft, ChevronRight, Coins, History, Package, PackageOpen, RotateCw } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import PokemonCardImage from '@/components/education/PokemonCardImage';
import { useAuth } from '@/contexts/AuthContext';
import { createDateFormatter } from '@/lib/format';
import type { PokemonCard } from '@/pages/Settings/pokemonApi';
import { cn } from '@/lib/utils';
import { createRequestKeyTracker } from '@/pages/ChatAgent/hooks/utils/requestKey';
import { useEducationHomeworkDictionaries, useEducationMembers } from './queries';
import { householdToday } from './calendarDates';
import { rewardCardImageUrl, rewardError, type OpenedRewardPack, type PurchaseRequest, type RewardLevel } from './rewardsApi';
import { useRewardActions, useRewardRecords, useRewardSettings, useRewardSync } from './rewardsQueries';
import { clearPendingPurchase, pendingPurchaseKey, readPendingPurchase, savePendingPurchase } from './rewardPurchases';
import RewardPackReveal from './RewardPackReveal';
import RewardProbabilities from './RewardProbabilities';
import pokemonball from '@/assets/img/pokemonball.svg';
import '../Settings/PokemonCardsPage.css';
import './RewardsPage.css';

type View = 'packs' | 'shop' | 'collection' | 'transactions';
const sources = { daily: '每日完成', streak: '连续学习', purchase: '积分兑换' };
const packTypes = ['daily', 'featured', 'rare'] as const;
function Pagination({ page, total, onChange, busy }: { page: number; total: number; onChange: (value: number) => void; busy: boolean }) {
  return <nav className="pokemon-catalog-pagination" aria-label="奖励分页"><Button variant="outline" size="icon" title="上一页" aria-label="上一页" disabled={busy || page <= 1} onClick={() => onChange(page - 1)}><ChevronLeft size={18} /></Button>
    <span>{page} / {Math.max(1, Math.ceil(total / 20))} 页</span><Button variant="outline" size="icon" title="下一页" aria-label="下一页" disabled={busy || page >= Math.ceil(total / 20)} onClick={() => onChange(page + 1)}><ChevronRight size={18} /></Button></nav>;
}

function StudentRewards({ studentId, today }: { studentId: string; today: string }) {
  const { member } = useAuth(); useTranslation(); const canAct = member?.role === 'student';
  const { query: settings } = useRewardSettings(); const summary = useRewardSync(studentId, today);
  const [view, setView] = useState<View>('packs'); const [page, setPage] = useState(1); const [level, setLevel] = useState<RewardLevel | ''>(''); const [series, setSeries] = useState('');
  const packs = useRewardRecords(studentId, 'packs', { page, page_size: 20, unopened: true }, view === 'packs');
  const cards = useRewardRecords(studentId, 'collection', { page, page_size: 20, ...(level ? { level } : {}), ...(series ? { set_code: series } : {}) }, view === 'collection');
  const transactions = useRewardRecords(studentId, 'transactions', { page, page_size: 20 }, view === 'transactions');
  const actions = useRewardActions(studentId); const [error, setError] = useState(''); const busy = actions.purchase.isPending || actions.open.isPending;
  const [selectedCard, setSelectedCard] = useState<PokemonCard | null>(null); const [result, setResult] = useState<OpenedRewardPack | null>(null);
  const purchaseKey = pendingPurchaseKey(member?.household_id ?? '', studentId);
  const [pending, setPending] = useState(() => canAct ? readPendingPurchase(purchaseKey) : null);
  const [confirm, setConfirm] = useState<PurchaseRequest | null>(pending); const purchaseGuard = useRef(false);
  const formatDate = createDateFormatter({ dateStyle: 'medium', timeStyle: 'short' });
  const switchView = (next: View) => { setView(next); setPage(1); setError(''); };
  const openPack = async (packId: string) => {
    if (busy || purchaseGuard.current) return;
    purchaseGuard.current = true; setError('');
    try { const opened = await actions.open.mutateAsync(packId); setResult(opened); setSelectedCard(opened.card); }
    catch (err) { setError(rewardError(err)); }
    finally { purchaseGuard.current = false; }
  };
  const buy = async () => {
    if (!confirm || busy || purchaseGuard.current) return;
    purchaseGuard.current = true; setError('');
    try { savePendingPurchase(purchaseKey, confirm); }
    catch { setError('浏览器无法保存兑换请求，请允许本地存储后重试。'); purchaseGuard.current = false; return; }
    setPending(confirm);
    try {
      await actions.purchase.mutateAsync(confirm);
      clearPendingPurchase(purchaseKey); setPending(null); setConfirm(null); switchView('packs');
    } catch (err) {
      setError(rewardError(err));
      if (isAxiosError(err) && err.response && err.response.status >= 400 && err.response.status < 500) {
        clearPendingPurchase(purchaseKey); setPending(null); setConfirm(null); void settings.refetch();
      }
    } finally { purchaseGuard.current = false; }
  };
  const displayed = view === 'packs' ? packs : view === 'collection' ? cards : transactions;

  return <>
    <section className="rewards-summary" aria-label="学习奖励概览">
      <div className="reward-balance"><img src={pokemonball} width={40} height={40} alt="" /><div><span>可兑换积分</span><strong aria-label="可兑换积分">{summary.data?.balance ?? '—'}<small> 分</small></strong></div></div>
      <div><span>累计作业积分</span><strong>{summary.data?.homework_points ?? '—'}</strong></div>
      <div className="reward-streak"><span>连续学习日</span><strong>{summary.data?.streak ?? '—'}<small> 天</small></strong><progress aria-label="连续学习奖励进度" max={summary.data?.next_streak_node ?? 3} value={summary.data?.streak ?? 0} /><span>下次补给：第 {summary.data?.next_streak_node ?? 3} 天</span></div>
      <div><span>待打开卡包</span><strong>{summary.data?.unopened_count ?? '—'}</strong><span>{summary.data?.today_rewarded ? '今日补给已到账' : '今天全部完成后领取'}</span></div>
      <Button variant="ghost" size="icon" title="同步奖励" aria-label="同步奖励" disabled={summary.isFetching || busy} onClick={() => void summary.refetch()}><RotateCw size={18} /></Button>
    </section>
    {summary.isError && <div className="reward-notice" role="alert">{rewardError(summary.error)}<Button variant="ghost" onClick={() => void summary.refetch()}>重试</Button></div>}
    <div className="rewards-navigation"><nav aria-label="奖励视图">{([['packs', '补给包'], ['shop', '积分兑换'], ['collection', '我的卡牌']] as const).map(([key, label]) => <button type="button" key={key} className={cn(view === key && 'active')} aria-current={view === key ? 'page' : undefined} disabled={busy} onClick={() => switchView(key)}>{label}</button>)}</nav><Button variant="ghost" title="积分记录" onClick={() => switchView('transactions')} disabled={busy}><History size={16} />积分记录</Button></div>
    {pending && !confirm && <div className="reward-notice"><span>上次兑换尚未确认结果。</span><Button variant="outline" onClick={() => { setError(''); setConfirm(pending); }}>恢复兑换</Button></div>}
    {error && <p role="alert" className="reward-notice">{error}</p>}
    {view !== 'shop' && displayed.isLoading && <p role="status" className="rewards-empty">正在加载…</p>}
    {view !== 'shop' && displayed.isError && <div className="rewards-empty"><p role="alert">{rewardError(displayed.error)}</p><Button variant="outline" onClick={() => void displayed.refetch()}><RotateCw size={16} />重试</Button></div>}
    {view === 'packs' && packs.data && !packs.isError && <>{packs.data.total === 0 ? <div className="rewards-empty"><PackageOpen size={32} /><p>暂无待打开的卡包</p></div> : <section className="rewards-pack-grid" aria-label="待打开卡包">{packs.data.items.map(pack => <article className="reward-pack" data-pack-type={pack.pack_type} key={pack.pack_id}>
      <div className="reward-pack-art"><img src={pokemonball} width={56} height={56} alt="" /><Package size={22} aria-hidden="true" /></div><h2>{settings.data?.pack_names[pack.pack_type] ?? '补给包'}</h2><p>{sources[pack.source]}{pack.streak_node ? ` · 第 ${pack.streak_node} 天` : ''}</p><time>{pack.reward_date}</time>
      {canAct && <Button disabled={busy || summary.isError} onClick={() => void openPack(pack.pack_id)}><PackageOpen size={16} />{actions.open.isPending && actions.open.variables === pack.pack_id ? '正在打开…' : '打开卡包'}</Button>}
    </article>)}</section>}<Pagination page={packs.data.page} total={packs.data.total} onChange={setPage} busy={packs.isFetching || busy} /></>}
    {view === 'shop' && <>{settings.isLoading && <p className="rewards-empty" role="status">正在加载卡包…</p>}{settings.isError && <div className="rewards-empty"><p role="alert">无法加载兑换价格。</p><Button variant="outline" onClick={() => void settings.refetch()}>重试</Button></div>}{settings.data && <section className="rewards-pack-grid" aria-label="可兑换卡包">{packTypes.map(type => <article className="reward-pack" data-pack-type={type} key={type}>
      <div className="reward-pack-art"><img src={pokemonball} width={56} height={56} alt="" /><Package size={22} aria-hidden="true" /></div><h2>{settings.data.pack_names[type]}</h2><p className="reward-price"><Coins size={15} />{settings.data.prices[type]} 分 · 1 张卡</p><RewardProbabilities values={settings.data.effective_probabilities[type]} settings={settings.data} />
      {canAct && <Button disabled={busy || Boolean(pending) || !summary.data || summary.isError || summary.data.balance < settings.data.prices[type] || !Object.values(settings.data.effective_probabilities[type]).some(Boolean)} onClick={() => { setError(''); setConfirm({ pack_type: type, expected_price: settings.data.prices[type], idempotency_key: createRequestKeyTracker().take(type) }); }}><Package size={16} />兑换{settings.data.pack_names[type]}</Button>}
    </article>)}</section>}</>}
    {view === 'collection' && <><div className="reward-filters"><label>等级<select aria-label="卡牌奖励等级" value={level} onChange={e => { setLevel(e.target.value as RewardLevel | ''); setPage(1); }}><option value="">全部等级</option>{Object.entries(settings.data?.level_names ?? {}).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label><label>系列<select aria-label="收藏系列" value={series} onChange={e => { setSeries(e.target.value); setPage(1); }}><option value="">全部系列</option>{(cards.data?.series ?? []).map(item => <option key={item.set_code} value={item.set_code}>{item.series_name}</option>)}</select></label><span>{cards.data?.total ?? 0} 种卡牌</span></div>
      {cards.data && !cards.isError && <>{cards.data.total === 0 ? <p className="rewards-empty">暂无收藏卡牌</p> : <section className="pokemon-catalog-grid" aria-label="收藏卡牌">{cards.data.items.map(card => <article className="pokemon-catalog-card" key={card.card_id}><button className="pokemon-card-open" aria-label={`查看${card.name} · ${card.card_number}`} onClick={() => { setResult(null); setSelectedCard(card); }} /><PokemonCardImage key={`${studentId}/${card.card_id}`} card={card} url={rewardCardImageUrl(card.card_id, studentId)} /><div className="pokemon-card-caption"><h2>{card.name}</h2><p>{card.series_name}</p><div><span>{settings.data?.level_names[card.reward_level] ?? card.rarity}</span><span>× {card.quantity}</span></div></div></article>)}</section>}<Pagination page={cards.data.page} total={cards.data.total} onChange={setPage} busy={cards.isFetching} /></>}
    </>}
    {view === 'transactions' && transactions.data && !transactions.isError && <><h2 className="reward-record-heading">积分记录</h2>{transactions.data.total === 0 ? <p className="rewards-empty">暂无积分记录</p> : <ol className="reward-transactions">{transactions.data.items.map(entry => <li key={entry.entry_id}><div><strong>{entry.kind === 'homework' ? entry.task_title ?? '完成作业' : `${entry.kind === 'purchase' ? '兑换' : '重复卡返分'} · ${entry.pack_type ? settings.data?.pack_names[entry.pack_type] ?? '卡包' : ''}`}</strong><time>{formatDate(new Date(entry.created_at))}</time></div><span>{entry.amount > 0 ? '+' : ''}{entry.amount} 分</span></li>)}</ol>}<Pagination page={transactions.data.page} total={transactions.data.total} onChange={setPage} busy={transactions.isFetching} /></>}
    <Dialog open={Boolean(confirm)} onOpenChange={open => { if (!open && !busy) setConfirm(null); }}><DialogContent variant="centered" className="reward-purchase-dialog"><DialogHeader><DialogTitle>{pending ? '恢复兑换' : '确认兑换'}</DialogTitle><DialogDescription>{confirm ? settings.data?.pack_names[confirm.pack_type] ?? '补给包' : ''} · {confirm?.expected_price} 分 · 1 张卡</DialogDescription></DialogHeader><p>当前余额 {summary.data?.balance ?? '—'} 分{pending ? '，此请求只结算一次。' : `，兑换后剩余 ${Math.max(0, (summary.data?.balance ?? 0) - (confirm?.expected_price ?? 0))} 分。`}</p>{confirm && settings.data && <RewardProbabilities values={settings.data.probabilities[confirm.pack_type]} settings={settings.data} />}{error && <p role="alert">{error}</p>}<DialogFooter><Button variant="outline" disabled={busy} onClick={() => setConfirm(null)}>稍后</Button><Button disabled={busy} onClick={() => void buy()}>{busy ? '正在确认…' : pending ? '重试原兑换' : '确认兑换'}</Button></DialogFooter></DialogContent></Dialog>
    <RewardPackReveal card={selectedCard} result={result} studentId={studentId} settings={settings.data} onClose={() => { setSelectedCard(null); setResult(null); }} />
  </>;
}

export default function RewardsPage() {
  const { member } = useAuth(); const [params, setParams] = useSearchParams(); const members = useEducationMembers(member?.role === 'parent'); const dictionaries = useEducationHomeworkDictionaries();
  const students = (members.data ?? []).filter(child => child.role === 'student'); const selected = params.get('student') ?? students[0]?.user_id ?? '';
  const studentId = member?.role === 'student' ? member.user_id : students.some(child => child.user_id === selected) ? selected : '';
  const [clock, setClock] = useState(() => new Date());
  useEffect(() => {
    const refresh = () => setClock(new Date()); const timer = window.setInterval(refresh, 60_000);
    window.addEventListener('focus', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); };
  }, []);
  const today = dictionaries.data ? householdToday(dictionaries.data.timezone, clock) : '';
  return <main className="rewards-page"><div className="rewards-shell"><Link className="rewards-back" to="/education"><ArrowLeft size={16} aria-hidden="true" />家庭作业</Link><header className="rewards-header"><h1>学习补给站</h1>{member?.role === 'parent' && <label>孩子<select aria-label="查看孩子的奖励" value={studentId} onChange={e => setParams({ student: e.target.value })}><option value="" disabled>选择孩子</option>{students.map(child => <option key={child.user_id} value={child.user_id}>{child.name}</option>)}</select></label>}</header>
    {dictionaries.isError && <div className="reward-notice" role="alert">无法读取家庭时区。<Button variant="outline" onClick={() => void dictionaries.refetch()}>重试</Button></div>}
    {studentId ? <StudentRewards key={studentId} studentId={studentId} today={today} /> : <div className="rewards-empty">{members.isError ? <><p>无法加载家庭账户。</p><Button onClick={() => void members.refetch()}>重试</Button></> : members.isLoading ? '正在加载…' : '暂无学生账户'}</div>}
  </div></main>;
}
