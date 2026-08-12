import { useEffect, useMemo, useState } from 'react';
import { BookOpen, CheckCircle2, ChevronLeft, ListTree, Send } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import Markdown from '@/pages/ChatAgent/components/Markdown';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { useLearningChatSpace, useStudentLearning, useTextbookMutations } from './queries';
import { sendChatMessageStream } from '@/pages/ChatAgent/utils/api';
import type { TextbookChapter, TextbookQuestion } from './types';

function QuestionPanel({ assignmentId, question }: { assignmentId: string; question: TextbookQuestion }) {
  const [selected, setSelected] = useState(question.selected_option ?? '');
  const [result, setResult] = useState<boolean | null>(question.is_correct ?? null);
  const mutations = useTextbookMutations();
  const submit = async () => {
    const answer = await mutations.answer.mutateAsync({ assignmentId, questionId: question.question_id, selectedOption: selected });
    setResult(answer.is_correct);
  };
  return <section className="border-t pt-4" style={{ borderColor: 'var(--color-border-muted)' }}><p className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{question.knowledge_point}</p><h3 className="mt-2 text-sm font-medium leading-6" style={{ color: 'var(--color-text-primary)' }}>{question.prompt}</h3><fieldset className="mt-3 grid gap-2">{Object.entries(question.options).map(([key, value]) => <label key={key} className="flex min-h-11 cursor-pointer items-center gap-3 border px-3 py-2 text-sm" style={{ borderColor: selected === key ? 'var(--color-accent)' : 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}><input type="radio" name={question.question_id} aria-label={`${key}. ${value}`} checked={selected === key} onChange={() => setSelected(key)} />{key}. {value}</label>)}</fieldset>{result === null ? <Button className="mt-3" size="sm" onClick={() => void submit()} disabled={!selected || mutations.answer.isPending}>提交答案</Button> : <p className="mt-3 flex items-center gap-2 text-sm" style={{ color: result ? 'var(--color-success)' : 'var(--color-text-secondary)' }}><CheckCircle2 className="size-4" />{result ? '回答正确' : `建议复习：${question.explanation ?? '回到学习材料后再看一次。'}`}</p>}</section>;
}

function ChapterDirectory({ assignmentId, chapters, activeChapterId }: { assignmentId: string; chapters: TextbookChapter[]; activeChapterId: string }) {
  return <nav aria-label="章节目录" className="grid gap-1"><p className="mb-2 flex items-center gap-2 font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}><ListTree className="size-3.5" aria-hidden="true" />目录</p>{chapters.map((item) => <Link key={item.chapter_id} to={`/education/learn/${assignmentId}/${item.chapter_id}`} className="border-l-2 px-3 py-2 text-sm" style={{ borderColor: item.chapter_id === activeChapterId ? 'var(--color-accent)' : 'transparent', color: item.chapter_id === activeChapterId ? 'var(--color-text-primary)' : 'var(--color-text-secondary)' }}>{item.position}. {item.title}</Link>)}</nav>;
}

function KnowledgeChecks({ assignmentId, chapter }: { assignmentId: string; chapter: TextbookChapter }) {
  return <section><div className="flex items-center gap-2"><BookOpen className="size-4" style={{ color: 'var(--color-text-secondary)' }} /><h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>知识检查</h2></div><div className="mt-4 grid gap-5">{chapter.questions.map((question) => <QuestionPanel key={question.question_id} assignmentId={assignmentId} question={question} />)}</div></section>;
}

function MobileLearningPanels({ assignmentId, chapters, chapter }: { assignmentId: string; chapters: TextbookChapter[]; chapter: TextbookChapter }) {
  return <div className="flex gap-2 lg:hidden"><Dialog><DialogTrigger asChild><Button size="sm" variant="outline"><ListTree className="mr-2 size-4" aria-hidden="true" />目录</Button></DialogTrigger><DialogContent><DialogHeader><DialogTitle>章节目录</DialogTitle></DialogHeader><ChapterDirectory assignmentId={assignmentId} chapters={chapters} activeChapterId={chapter.chapter_id} /></DialogContent></Dialog><Dialog><DialogTrigger asChild><Button size="sm" variant="outline"><BookOpen className="mr-2 size-4" aria-hidden="true" />知识检查</Button></DialogTrigger><DialogContent><DialogHeader><DialogTitle>本章检查</DialogTitle></DialogHeader><KnowledgeChecks assignmentId={assignmentId} chapter={chapter} /></DialogContent></Dialog></div>;
}

function ChapterReader({ assignmentId, chapter }: { assignmentId: string; chapter: TextbookChapter }) {
  const markLearning = useTextbookMutations().progress.mutateAsync;
  useEffect(() => { if (chapter.progress_status === 'not_started') void markLearning({ assignmentId, chapterId: chapter.chapter_id, status: 'learning' }); }, [assignmentId, chapter.chapter_id, chapter.progress_status, markLearning]);
  return <article className="min-w-0"><div className="border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}><p className="font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>CHAPTER {chapter.position}</p><h2 className="title-font mt-2 text-2xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>{chapter.title}</h2></div><div className="py-6"><Markdown variant="panel" content={chapter.markdown} className="text-base leading-7" /><div className="mt-8 border-l-2 px-4 py-1" style={{ borderColor: 'var(--color-border-muted)' }}><Markdown variant="compact" content={chapter.teaching_material} className="text-sm" /></div></div></article>;
}

function LearningChat({ assignmentId, chapterId }: { assignmentId: string; chapterId: string }) {
  const [message, setMessage] = useState('');
  const [answer, setAnswer] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const chatSpace = useLearningChatSpace(assignmentId);
  const submit = async () => {
    const question = message.trim();
    if (!question || !chatSpace.data) return;
    setSending(true);
    setError('');
    setAnswer('');
    try {
      await sendChatMessageStream(
        question,
        chatSpace.data.workspace_id,
        chatSpace.data.conversation_thread_id,
        [],
        false,
        (event) => {
          if (event.event === 'message_chunk' && event.role === 'assistant' && typeof event.content === 'string') {
            setAnswer((current) => current + event.content);
          }
        },
        null,
        'flash',
        'zh-CN',
        Intl.DateTimeFormat().resolvedOptions().timeZone,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        { assignmentId, chapterId },
      );
      setMessage('');
    } catch {
      setError('暂时无法发送问题，请稍后重试。');
    } finally {
      setSending(false);
    }
  };
  return <section className="border-t pt-6" style={{ borderColor: 'var(--color-border-muted)' }}><h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>章节问答</h2><p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>围绕当前章节提问。</p><div className="mt-4 grid gap-3"><label className="sr-only" htmlFor="learning-question">问题</label><textarea id="learning-question" value={message} onChange={(event) => setMessage(event.target.value)} className="min-h-24 w-full resize-y border bg-background p-3 text-sm" style={{ borderColor: 'var(--color-border-muted)' }} placeholder="写下你的问题" /><div className="flex justify-end"><Button size="sm" onClick={() => void submit()} disabled={!message.trim() || sending || chatSpace.isLoading || !chatSpace.data}>{sending ? '正在回答' : <><Send className="mr-2 size-4" aria-hidden="true" />提问</>}</Button></div>{chatSpace.isError && <p className="text-sm" role="alert" style={{ color: 'var(--color-danger)' }}>学习问答暂不可用，请稍后重试。</p>}{error && <p className="text-sm" role="alert" style={{ color: 'var(--color-danger)' }}>{error}</p>}{answer && <div className="border-l-2 pl-4 text-sm leading-6" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>{answer}</div>}</div></section>;
}

export default function StudentLearningPage() {
  const { assignmentId, chapterId } = useParams();
  const learning = useStudentLearning(assignmentId);
  const data = learning.data;
  const chapter = useMemo(() => data?.chapters.find((item) => item.chapter_id === chapterId) ?? data?.chapters[0], [chapterId, data?.chapters]);
  if (learning.isLoading) return <main className="h-full overflow-y-auto bg-canvas"><p className="p-8 text-sm text-muted-foreground">正在加载学习材料…</p></main>;
  if (!data || !chapter) return <main className="h-full overflow-y-auto bg-canvas"><p className="p-8 text-sm text-muted-foreground">学习材料不存在或无权访问。</p></main>;
  return <main className="h-full min-h-0 overflow-y-auto bg-canvas" data-testid="student-learning-page"><div className="mx-auto grid w-full max-w-[1500px] gap-0 px-4 sm:px-6 lg:grid-cols-[220px_minmax(0,1fr)_310px] lg:px-6"><aside className="hidden lg:block lg:min-h-[calc(100dvh-80px)] lg:border-r lg:py-8 lg:pr-4" style={{ borderColor: 'var(--color-border-muted)' }}><Link to="/education" className="inline-flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}><ChevronLeft className="size-4" />我的学习</Link><p className="title-font mt-5 text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>{data.textbook_title}</p><div className="mt-5"><ChapterDirectory assignmentId={data.assignment_id} chapters={data.chapters} activeChapterId={chapter.chapter_id} /></div></aside><section className="min-w-0 py-6 lg:px-10 lg:py-8"><div className="mb-6 border-b pb-4 lg:hidden" style={{ borderColor: 'var(--color-border-muted)' }}><Link to="/education" className="inline-flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}><ChevronLeft className="size-4" />我的学习</Link><h1 className="title-font mt-4 text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>{data.textbook_title}</h1><div className="mt-4"><MobileLearningPanels assignmentId={data.assignment_id} chapters={data.chapters} chapter={chapter} /></div></div><ChapterReader assignmentId={data.assignment_id} chapter={chapter} /><LearningChat assignmentId={data.assignment_id} chapterId={chapter.chapter_id} /></section><aside className="hidden lg:block lg:border-l lg:py-8 lg:pl-6" style={{ borderColor: 'var(--color-border-muted)' }}><KnowledgeChecks assignmentId={data.assignment_id} chapter={chapter} /></aside></div></main>;
}
