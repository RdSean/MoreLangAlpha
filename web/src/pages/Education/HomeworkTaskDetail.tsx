import { ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useEducationAssetDownloadUrl, useEducationTaskDetail } from './queries';
import type { EducationTaskAsset } from './types';

function Attachment({ asset }: { asset: EducationTaskAsset }) {
  const download = useEducationAssetDownloadUrl(asset.asset_id);
  if (download.isError) return <Button variant="ghost" size="sm" onClick={() => void download.refetch()}>重试加载：{asset.original_filename}</Button>;
  if (!download.data) return <span className="text-xs text-muted-foreground">正在加载 {asset.original_filename}…</span>;
  return <a href={download.data} target="_blank" rel="noopener noreferrer" className="flex min-h-11 items-center gap-2 break-all text-sm underline underline-offset-4"><ExternalLink className="size-4 shrink-0" aria-hidden="true" />{asset.original_filename}</a>;
}

/** Only mounted when a task dialog is open; the calendar does not fetch N timelines. */
export default function HomeworkTaskDetail({ taskId }: { taskId: string }) {
  const detail = useEducationTaskDetail(taskId);
  if (detail.isLoading) return <p role="status" className="text-sm text-muted-foreground">正在加载作业记录…</p>;
  if (detail.isError) return <div><p role="alert" className="text-sm">作业记录加载失败。</p><Button variant="outline" size="sm" onClick={() => void detail.refetch()}>重试</Button></div>;
  if (!detail.data) return null;
  return <div className="grid max-h-[40vh] gap-4 overflow-y-auto rounded-md border p-3">
    {detail.data.parent_materials.length > 0 && <section><h3 className="text-sm font-semibold">作业材料</h3>{detail.data.parent_materials.map(asset => <Attachment key={asset.asset_id} asset={asset} />)}</section>}
    {!detail.data.submissions.length && <p className="text-sm text-muted-foreground">尚未打卡。</p>}
    {detail.data.submissions.map(submission => <article key={submission.submission_id} className="border-b pb-3 last:border-0 last:pb-0">
      <h3 className="mb-2 text-xs font-medium text-muted-foreground">第 {submission.sequence} 次提交{submission.submission_kind === 'revision' ? ' · 补充' : ' · 打卡'}</h3>
      <p className="whitespace-pre-wrap break-words text-sm">{submission.submission_text || '已确认完成。'}</p>
      {submission.assets.map(asset => <Attachment key={asset.asset_id} asset={asset} />)}
      {submission.reviews.map(review => <p key={review.review_id} className="mt-2 whitespace-pre-wrap break-words border-l-2 pl-3 text-sm text-muted-foreground">{review.decision === 'revision_requested' ? '修改建议' : '家长反馈'}：{review.feedback_text}</p>)}
    </article>)}
  </div>;
}
