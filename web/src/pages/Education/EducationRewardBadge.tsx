import { Gift } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useRewardSync } from './rewardsQueries';

export default function EducationRewardBadge({ selectedStudentId, today }: { selectedStudentId: string; today: string }) {
  const { member } = useAuth(); const studentId = member?.role === 'student' ? member.user_id : selectedStudentId;
  const rewards = useRewardSync(studentId, today);
  return <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-l pl-3">
    {studentId && <div><p className="text-xs text-muted-foreground">可兑换积分</p><p className="text-xl font-semibold tabular-nums" aria-label="可兑换积分">{rewards.isError ? '—' : rewards.data?.balance ?? '—'} <span className="text-xs font-normal text-muted-foreground">分</span></p></div>}
    <Link className="inline-flex min-h-11 items-center gap-1.5 text-sm" to={`/education/rewards${member?.role === 'parent' && studentId ? `?student=${encodeURIComponent(studentId)}` : ''}`}><Gift size={16} aria-hidden="true" />学习奖励{rewards.data && rewards.data.unopened_count > 0 ? ` · ${rewards.data.unopened_count}` : ''}</Link>
  </div>;
}
