import { useState } from 'react';
import { ArrowLeft, Save } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/contexts/AuthContext';
import { useRewardSettings } from '@/pages/Education/rewardsQueries';
import { rewardError, type PackType, type RewardSettings } from '@/pages/Education/rewardsApi';
import RewardProbabilities from '@/pages/Education/RewardProbabilities';
import '@/pages/Education/RewardsPage.css';

function PriceEditor({ initial }: { initial: RewardSettings }) {
  const { query, save } = useRewardSettings(); const settings = query.data ?? initial;
  const [prices, setPrices] = useState<Record<PackType, string>>({ daily: String(initial.prices.daily), featured: String(initial.prices.featured), rare: String(initial.prices.rare) });
  const [message, setMessage] = useState('');
  const valid = Object.values(prices).every(value => /^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 10000);
  return <form className="reward-settings" onSubmit={event => {
    event.preventDefault(); if (!valid) return; setMessage('');
    void save.mutateAsync({ daily: Number(prices.daily), featured: Number(prices.featured), rare: Number(prices.rare) }).then(updated => {
      setPrices({ daily: String(updated.prices.daily), featured: String(updated.prices.featured), rare: String(updated.prices.rare) }); setMessage('已保存家庭卡包价格。');
    }).catch(() => {});
  }}>
    {(['daily', 'featured', 'rare'] as const).map(type => <section key={type} className="reward-price-setting"><div><h2>{settings.pack_names[type]}</h2><RewardProbabilities values={settings.probabilities[type]} settings={settings} /></div><label htmlFor={`reward-price-${type}`}>兑换价格<span className="reward-price-input"><Input id={`reward-price-${type}`} aria-label={`${settings.pack_names[type]}价格`} type="number" min={1} max={10000} step={1} inputMode="numeric" required disabled={save.isPending} value={prices[type]} onChange={event => { setMessage(''); setPrices(previous => ({ ...previous, [type]: event.target.value })); }} /><span>分</span></span></label></section>)}
    <footer><div aria-live="polite">{save.isError ? <p role="alert">{rewardError(save.error)}</p> : message}</div><Button type="submit" disabled={!valid || save.isPending}><Save size={16} />{save.isPending ? '保存中…' : '保存设置'}</Button></footer>
  </form>;
}

export default function RewardSettingsPage() {
  const { member } = useAuth(); const settings = useRewardSettings();
  return <main className="rewards-page"><div className="reward-settings-shell"><Link className="rewards-back" to="/settings?tab=family"><ArrowLeft size={16} aria-hidden="true" />家庭账户</Link><header className="rewards-header"><h1>奖励设置</h1></header>
    {member?.role !== 'parent' ? <p className="rewards-empty">只有家长可以修改奖励价格。</p> : settings.query.isLoading ? <p role="status" className="rewards-empty">正在加载…</p> : settings.query.isError ? <div className="rewards-empty"><p role="alert">无法加载奖励设置。</p><Button variant="outline" onClick={() => void settings.query.refetch()}>重试</Button></div> : settings.query.data && <PriceEditor key={member.household_id} initial={settings.query.data} />}
  </div></main>;
}
