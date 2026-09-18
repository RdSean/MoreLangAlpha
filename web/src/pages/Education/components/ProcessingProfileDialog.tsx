import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

export interface ProcessingProfileValue {
  subject: 'english' | 'math' | 'chinese' | 'science' | 'other';
  grade_band: 'primary' | 'middle' | 'high' | 'adult';
  language: 'zh-CN' | 'en' | 'bilingual';
  depth: 'overview' | 'standard' | 'deep';
  question_types: Array<'choice' | 'fill' | 'short_answer' | 'mixed'>;
  prompt_fragment: string;
  allowed_skills: string[];
}

export default function ProcessingProfileDialog({
  open,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (profile: ProcessingProfileValue) => Promise<void>;
}) {
  const [subject, setSubject] = useState<ProcessingProfileValue['subject']>('english');
  const [gradeBand, setGradeBand] = useState<ProcessingProfileValue['grade_band']>('middle');
  const [language, setLanguage] = useState<ProcessingProfileValue['language']>('zh-CN');
  const [depth, setDepth] = useState<ProcessingProfileValue['depth']>('standard');
  const [questionTypes, setQuestionTypes] = useState<ProcessingProfileValue['question_types']>(['choice', 'mixed']);
  const [promptFragment, setPromptFragment] = useState('');

  const toggleQuestionType = (kind: ProcessingProfileValue['question_types'][number]) => {
    setQuestionTypes((current) => current.includes(kind) ? current.filter((item) => item !== kind) : [...current, kind]);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent variant="centered" className="max-w-xl">
        <DialogHeader><DialogTitle>教材处理设置</DialogTitle></DialogHeader>
        <div className="grid gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm">学科<select value={subject} onChange={(event) => setSubject(event.target.value as ProcessingProfileValue['subject'])} className="h-10 border bg-background px-3"><option value="english">英语</option><option value="math">数学</option><option value="chinese">语文</option><option value="science">科学</option><option value="other">其他</option></select></label>
            <label className="grid gap-1.5 text-sm">学段<select value={gradeBand} onChange={(event) => setGradeBand(event.target.value as ProcessingProfileValue['grade_band'])} className="h-10 border bg-background px-3"><option value="primary">小学</option><option value="middle">初中</option><option value="high">高中</option><option value="adult">成人</option></select></label>
            <label className="grid gap-1.5 text-sm">讲解语言<select value={language} onChange={(event) => setLanguage(event.target.value as ProcessingProfileValue['language'])} className="h-10 border bg-background px-3"><option value="zh-CN">中文</option><option value="en">英文</option><option value="bilingual">双语</option></select></label>
            <label className="grid gap-1.5 text-sm">讲解深度<select value={depth} onChange={(event) => setDepth(event.target.value as ProcessingProfileValue['depth'])} className="h-10 border bg-background px-3"><option value="overview">概要</option><option value="standard">标准</option><option value="deep">深入</option></select></label>
          </div>
          <fieldset><legend className="text-sm font-medium">题型偏好</legend><div className="mt-2 flex flex-wrap gap-3 text-sm">{([['choice', '选择'], ['fill', '填空'], ['short_answer', '问答'], ['mixed', '混合']] as const).map(([value, label]) => <label key={value} className="flex items-center gap-2"><input type="checkbox" checked={questionTypes.includes(value)} onChange={() => toggleQuestionType(value)} />{label}</label>)}</div></fieldset>
          <label className="grid gap-1.5 text-sm">补充要求<textarea value={promptFragment} onChange={(event) => setPromptFragment(event.target.value)} maxLength={2000} className="min-h-24 border bg-background p-3" placeholder="例如：重点训练阅读策略，解释尽量简洁" /></label>
          <DialogFooter><Button onClick={() => void onConfirm({ subject, grade_band: gradeBand, language, depth, question_types: questionTypes, prompt_fragment: promptFragment, allowed_skills: [] })} disabled={questionTypes.length === 0}>开始结构分析</Button></DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
