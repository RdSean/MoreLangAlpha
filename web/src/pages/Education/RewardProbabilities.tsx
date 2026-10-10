import type { RewardLevel, RewardSettings } from './rewardsApi';

export default function RewardProbabilities({ values, settings }: { values: Partial<Record<RewardLevel, number>>; settings: RewardSettings }) {
  return <dl className="reward-probabilities">{Object.entries(values).filter(([, probability]) => probability > 0).map(([level, probability]) => <div key={level}><dt>{settings.level_names[level as RewardLevel]}</dt><dd>{Math.round(probability * 10000) / 100}%</dd></div>)}</dl>;
}
