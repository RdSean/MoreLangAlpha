import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowLeft, ChevronLeft, ChevronRight, Keyboard, Mic, Send, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ui/loader';
import { speechSupported, useVoiceInput } from '@/components/ui/chat-input.useVoiceInput';
import { useBookQuestions, useBookReadingMutation, useLessonQuestion } from '../queries';
import EducationMarkdown from './EducationMarkdown';
import './LessonConversation.css';

interface AnswerPage { question: string; answer: string; error?: string }

function answerPages(messages: Array<{ role: 'user' | 'assistant'; content: string }>): AnswerPage[] {
  const pages: AnswerPage[] = [];
  for (const message of messages) {
    if (message.role === 'user') pages.push({ question: message.content, answer: '' });
    else if (pages.length) pages[pages.length - 1].answer += message.content;
  }
  return pages;
}

export default function LessonConversation({ textbookId, knowledgePointId, assignmentId, children }: {
  textbookId: string; knowledgePointId: string; assignmentId?: string; children: ReactNode;
}) {
  const history = useBookQuestions(textbookId, knowledgePointId, assignmentId);
  const questionMutation = useLessonQuestion();
  const reading = useBookReadingMutation(textbookId);
  const [message, setMessage] = useState('');
  const [voiceMode, setVoiceMode] = useState(false);
  const [sending, setSending] = useState(false);
  const [pages, setPages] = useState<AnswerPage[]>([]);
  const [page, setPage] = useState(0);
  const hydrated = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const submitGuard = useRef(false);
  const voiceHeld = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { isListening, toggleListening, stopListening } = useVoiceInput({ message, setMessage, isLoading: sending });
  const markRef = useRef(reading.mutate);
  markRef.current = reading.mutate;

  useEffect(() => {
    markRef.current({ knowledgePointId, state: 'viewed' });
    return () => { controller.current?.abort(); };
  }, [knowledgePointId]);
  useEffect(() => {
    if (hydrated.current || history.isFetching || !history.data) return;
    setPages(answerPages(history.data));
    hydrated.current = true;
  }, [history.data, history.isFetching]);
  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = 0; }, [page]);

  const submit = async () => {
    const question = message.trim();
    if (!question || submitGuard.current || history.isLoading || history.isFetching) return;
    submitGuard.current = true;
    stopListening();
    setSending(true);
    setMessage('');
    hydrated.current = true;
    const index = pages.length;
    setPages((current) => [...current, { question, answer: '' }]);
    setPage(index + 1);
    const abort = new AbortController();
    controller.current = abort;
    let answer = '';
    let streamError = '';
    const update = (patch: Partial<AnswerPage>) => setPages((current) => current.map((entry, i) => i === index ? { ...entry, ...patch } : entry));
    try {
      await questionMutation.mutateAsync({ textbookId, assignmentId, knowledgePointId, question, signal: abort.signal,
        onEvent: (event) => {
          if (event.event === 'message_chunk' && event.role === 'assistant' && (event.content_type ?? 'text') === 'text' && typeof event.content === 'string') {
            answer += event.content;
            update({ answer });
          } else if (event.event === 'error' || event.event === 'retry') {
            streamError = typeof event.message === 'string' ? event.message : '回答暂时中断，请重新提问。';
          }
        },
      });
      if (abort.signal.aborted) return;
      if (streamError || !answer.trim()) throw new Error(streamError || '未收到回答，请重新提问。');
      markRef.current({ knowledgePointId, state: 'asked' });
    } catch {
      if (!abort.signal.aborted) {
        update({ error: streamError || '暂时无法完成回答，请稍后重试。' });
        setMessage(question);
      }
    } finally {
      if (!abort.signal.aborted) setSending(false);
      submitGuard.current = false;
    }
  };
  const current = pages[page - 1];
  return (
    <div className="lesson-conversation">
      {page === 0 ? <div className="lesson-original">{children}</div> : <section className="lesson-answer" aria-label="讲义问答">
        <header className="lesson-answer-header">
          <Button variant="ghost" size="icon" aria-label="返回讲义" title="返回讲义" onClick={() => setPage(0)}><ArrowLeft className="size-4" /></Button>
          <h1 className="min-w-0 flex-1 break-words text-base font-semibold">{current?.question}</h1>
        </header>
        <div ref={scrollRef} className="lesson-answer-scroll book-reader-prose" key={page}>
          {current?.answer && <EducationMarkdown content={current.answer} />}
          {sending && page === pages.length && <div className="flex items-center gap-2 text-xs text-muted-foreground" role="status"><Loader /><span>正在回答…</span></div>}
          {current?.error && <p role="alert" className="text-sm text-destructive">{current.error}</p>}
        </div>
      </section>}
      <footer className="lesson-composer">
        {(pages.length > 0 || history.isError) && <div className="lesson-page-controls">
          <Button variant="ghost" size="sm" onClick={() => setPage(0)} aria-pressed={page === 0}>讲义</Button>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="size-7" aria-label="上一页回答" title="上一页回答" disabled={page <= 0} onClick={() => setPage((value) => value - 1)}><ChevronLeft className="size-3.5" /></Button>
            <span className="w-16 text-center text-xs tabular-nums text-muted-foreground">{page} / {pages.length}</span>
            <Button variant="ghost" size="icon" className="size-7" aria-label="下一页回答" title="下一页回答" disabled={page >= pages.length} onClick={() => setPage((value) => value + 1)}><ChevronRight className="size-3.5" /></Button>
          </div>
          {history.isError && <button className="text-xs text-destructive" onClick={() => void history.refetch()}>重试加载记录</button>}
        </div>}
        <div className="lesson-composer-input">
          <Button variant="ghost" size="icon" className="size-9 shrink-0" aria-label={voiceMode ? '切换为文字输入' : '切换为语音输入'} title={voiceMode ? '文字输入' : speechSupported ? '语音输入' : '当前浏览器不支持语音'} disabled={sending || (!voiceMode && !speechSupported)} onClick={() => { stopListening(); setVoiceMode((value) => !value); }}>
            {voiceMode ? <Keyboard className="size-4" /> : <Mic className="size-4" />}
          </Button>
          {voiceMode ? <div className="min-w-0 flex-1">
            <button className="lesson-voice-button" type="button" aria-label={isListening ? '松开结束录音' : '按住说话'} disabled={sending}
              onPointerDown={(event) => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); voiceHeld.current = true; toggleListening(); }}
              onPointerUp={() => { voiceHeld.current = false; stopListening(); }}
              onPointerCancel={() => { voiceHeld.current = false; stopListening(); }}
              onLostPointerCapture={() => { if (voiceHeld.current) { voiceHeld.current = false; stopListening(); } }}
              onKeyDown={(event) => { if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) { event.preventDefault(); toggleListening(); } }}
              onKeyUp={(event) => { if (event.key === ' ' || event.key === 'Enter') stopListening(); }}>
              {isListening ? <><Square className="size-3" />松开结束录音</> : <><Mic className="size-4" />按住说话</>}
            </button>
            {message && <p className="mt-2 break-words text-sm" aria-live="polite">{message}</p>}
          </div> : <textarea aria-label="讲义问题" placeholder="就这份讲义提问…" value={message} disabled={sending}
            onChange={(event) => setMessage(event.target.value)} rows={2}
            onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void submit(); } }} />}
          <Button variant="ghost" size="icon" className="size-9 shrink-0" aria-label="发送问题" title="发送问题" disabled={!message.trim() || sending || isListening || history.isLoading || history.isFetching} onClick={() => void submit()}><Send className="size-4" /></Button>
        </div>
        {reading.isError && <p className="mt-1 text-xs text-destructive" role="status">学习状态保存失败</p>}
      </footer>
    </div>
  );
}
