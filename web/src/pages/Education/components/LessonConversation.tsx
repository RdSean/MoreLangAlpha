import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Keyboard, Mic, Send, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ui/loader';
import { speechSupported, useVoiceInput } from '@/components/ui/chat-input.useVoiceInput';
import { useBookQuestions, useBookReadingMutation, useLessonQuestion } from '../queries';
import { useScrollMemory } from '@/lib/scrollMemory';
import EducationMarkdown from './EducationMarkdown';
import './LessonConversation.css';

interface QuestionTurn { question: string; answer: string; error?: string }

function questionTurns(messages: Array<{ role: 'user' | 'assistant'; content: string }>): QuestionTurn[] {
  const turns: QuestionTurn[] = [];
  for (const message of messages) {
    if (message.role === 'user') turns.push({ question: message.content, answer: '' });
    else if (turns.length) turns[turns.length - 1].answer += message.content;
  }
  return turns;
}

export default function LessonConversation({ textbookId, knowledgePointId, assignmentId, readingPositionKey, children }: {
  textbookId: string; knowledgePointId: string; assignmentId?: string; readingPositionKey?: string; children: ReactNode;
}) {
  const history = useBookQuestions(textbookId, knowledgePointId, assignmentId);
  const questionMutation = useLessonQuestion();
  const reading = useBookReadingMutation(textbookId);
  const [message, setMessage] = useState('');
  const [voiceMode, setVoiceMode] = useState(false);
  const [sending, setSending] = useState(false);
  const [turns, setTurns] = useState<QuestionTurn[]>([]);
  const [historyReady, setHistoryReady] = useState(false);
  const [viewportHeight, setViewportHeight] = useState(0);
  const hydrated = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const submitGuard = useRef(false);
  const voiceHeld = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const turnRefs = useRef<Array<HTMLElement | null>>([]);
  const pendingScroll = useRef<number | null>(null);
  useScrollMemory(scrollRef, readingPositionKey ?? `lesson:${textbookId}:${assignmentId ?? ''}:${knowledgePointId}`, { persist: true, ready: historyReady });
  const { isListening, toggleListening, stopListening } = useVoiceInput({ message, setMessage, isLoading: sending });
  const markRef = useRef(reading.mutate);
  markRef.current = reading.mutate;

  useEffect(() => {
    markRef.current({ knowledgePointId, state: 'viewed' });
    return () => { controller.current?.abort(); };
  }, [knowledgePointId]);
  useEffect(() => {
    if (hydrated.current || history.isFetching || (!history.data && !history.isError)) return;
    setTurns(questionTurns(history.data ?? []));
    setHistoryReady(true);
    hydrated.current = true;
  }, [history.data, history.isFetching, history.isError]);
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const measure = () => setViewportHeight(container.clientHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const index = pendingScroll.current;
    const container = scrollRef.current;
    const target = index === null ? null : turnRefs.current[index];
    if (!container || !target) return;
    pendingScroll.current = null;
    container.scrollTo({
      top: container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
    });
  }, [turns.length]);

  const submit = async () => {
    const question = message.trim();
    if (!question || submitGuard.current || history.isLoading || history.isFetching) return;
    submitGuard.current = true;
    stopListening();
    setSending(true);
    setMessage('');
    hydrated.current = true;
    setHistoryReady(true);
    const index = turns.length;
    pendingScroll.current = index;
    setTurns((current) => [...current, { question, answer: '' }]);
    const abort = new AbortController();
    controller.current = abort;
    let answer = '';
    let streamError = '';
    const update = (patch: Partial<QuestionTurn>) => setTurns((current) => current.map((entry, i) => i === index ? { ...entry, ...patch } : entry));
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
  return (
    <div className="lesson-conversation">
      <div ref={scrollRef} className="lesson-conversation-scroll" role="region" aria-label="讲义与问答">
        <div className="lesson-original">{children}</div>
        {turns.map((turn, index) => <section key={index} ref={(node) => { turnRefs.current[index] = node; }} className="lesson-turn" aria-label={`第 ${index + 1} 轮问答`} style={index === turns.length - 1 ? { minHeight: viewportHeight } : undefined}>
          <div className="lesson-turn-question"><h2>{turn.question}</h2></div>
          <div className="lesson-turn-answer book-reader-prose">
            {turn.answer && <EducationMarkdown content={turn.answer} />}
            {sending && index === turns.length - 1 && <div className="flex items-center gap-2 text-xs text-muted-foreground" role="status"><Loader /><span>正在回答…</span></div>}
            {turn.error && <p role="alert" className="text-sm text-destructive">{turn.error}</p>}
          </div>
        </section>)}
      </div>
      <footer className="lesson-composer">
        {history.isError && <button className="mb-2 text-xs text-destructive" onClick={() => void history.refetch()}>重试加载记录</button>}
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
