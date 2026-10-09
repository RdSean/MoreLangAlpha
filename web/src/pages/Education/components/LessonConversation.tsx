import { lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode, type ComponentProps } from 'react';
import { FileText, Globe, Keyboard, Mic, Send, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Loader } from '@/components/ui/loader';
import { speechSupported, useVoiceInput } from '@/components/ui/chat-input.useVoiceInput';
import { useBookReadingMutation, useLessonChatSpace } from '../queries';
import { useLessonConversationSession } from '../hooks/useLessonConversationSession';
import type { LearningChatSpace } from '../types';
import type { ChatMessage, AssistantMessage } from '@/types/chat';
import { MessageBubble } from '@/pages/ChatAgent/components/messageList/MessageBubble';
import { MessageContentSegments } from '@/pages/ChatAgent/components/messageList/MessageContentSegments';
import { MessageActionsProvider } from '@/pages/ChatAgent/components/messageList/MessageActionsContext';
import { CitationMetadataProvider } from '@/pages/ChatAgent/components/CitationMetadataContext';
import { computeAgentArtifactRouting } from '@/pages/ChatAgent/utils/agentPaths';
import { getPreviewUrl } from '@/pages/ChatAgent/utils/api';
import type { PreviewData } from '@/pages/ChatAgent/hooks/utils/types';
import type { LessonArtifactReference } from '../hooks/useLessonConversationSession';
import { WorkspaceProvider } from '@/pages/ChatAgent/contexts/WorkspaceContext';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { useIsMobile } from '@/hooks/useIsMobile';
import { useScrollMemory } from '@/lib/scrollMemory';
import EducationMarkdown from './EducationMarkdown';
import './LessonConversation.css';

const FilePanel = lazy(() => import('@/pages/ChatAgent/components/FilePanel'));
const PreviewViewer = lazy(() => import('@/pages/ChatAgent/components/viewers/PreviewViewer'));
const renderLessonText = (content: string) => <EducationMarkdown content={content} />;
interface QuestionTurn { question?: ChatMessage; answers: AssistantMessage[] }
type LessonContent = ReactNode | ((state: { questionsBusy: boolean }) => ReactNode);

function questionTurns(messages: ChatMessage[]): QuestionTurn[] {
  const turns: QuestionTurn[] = [];
  for (const message of messages) {
    if (message.role === 'user') turns.push({ question: message, answers: [] });
    else if (message.role === 'assistant') {
      if (!turns.length) turns.push({ answers: [] });
      turns[turns.length - 1].answers.push(message);
    }
  }
  return turns;
}

export default function LessonConversation({ textbookId, knowledgePointId, assignmentId, readingPositionKey, children }: {
  textbookId: string; knowledgePointId: string; assignmentId?: string; readingPositionKey?: string; children: LessonContent;
}) {
  const space = useLessonChatSpace(textbookId, knowledgePointId, assignmentId);
  if (!space.data || space.isFetching) return <div className="lesson-conversation">
    <div className="lesson-conversation-scroll"><div className="lesson-original">{typeof children === 'function' ? children({ questionsBusy: true }) : children}</div></div>
    <footer className="lesson-composer"><textarea aria-label="讲义问题" disabled /><Button aria-label="发送问题" disabled><Send className="size-4" /></Button><Loader />{space.isError && <button onClick={() => void space.refetch()}>重试加载会话</button>}</footer>
  </div>;
  return <LessonSession key={`${textbookId}:${assignmentId ?? ''}:${knowledgePointId}:${space.data.conversation_thread_id}`}
    {...{ textbookId, knowledgePointId, assignmentId, readingPositionKey, children }} space={space.data} />;
}

function LessonSession({ textbookId, knowledgePointId, assignmentId, readingPositionKey, children, space }: {
  textbookId: string; knowledgePointId: string; assignmentId?: string; readingPositionKey?: string; children: LessonContent; space: LearningChatSpace;
}) {
  const session = useLessonConversationSession(space, textbookId, knowledgePointId, assignmentId);
  const isMobile = useIsMobile();
  const [file, setFile] = useState<{ path: string; workspaceId: string } | null>(null);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const previewRequest = useRef(0);
  const openPreview = async (reference: LessonArtifactReference) => {
    if (assignmentId) return;
    const request = ++previewRequest.current;
    const data = { ...reference.payload, url: '', loading: true, error: false } as unknown as PreviewData;
    setPreview(data);
    try {
      const resolved = await getPreviewUrl(space.workspace_id, data.port, data.command);
      const url = new URL(resolved.url);
      if (data.path) url.pathname = url.pathname.replace(/\/+$/, '') + data.path;
      if (request === previewRequest.current) setPreview({ ...data, url: url.toString(), loading: false });
    } catch {
      if (request === previewRequest.current) setPreview({ ...data, loading: false, error: true });
    }
  };
  const sendPromptRef = useRef<(prompt: string) => void>(() => {});
  const handleRetry = session.handleRetry;
  const actions = useMemo(() => ({
    onWidgetSendPrompt: (prompt: string) => sendPromptRef.current(prompt),
    onRetry: () => void handleRetry(),
    onApproveCreateWorkspace: session.handleApproveCreateWorkspace,
    onRejectCreateWorkspace: session.handleRejectCreateWorkspace,
    onApproveStartQuestion: session.handleApproveStartQuestion,
    onRejectStartQuestion: session.handleRejectStartQuestion,
    onApprovePTCAgent: session.handleApprovePTCAgent,
    onRejectPTCAgent: session.handleRejectPTCAgent,
    onApproveSecretaryAction: session.handleApproveSecretaryAction,
    onRejectSecretaryAction: session.handleRejectSecretaryAction,
    onAnswerQuestion: session.handleAnswerQuestion,
    onSkipQuestion: session.handleSkipQuestion,
    onApprovePlan: session.handleApproveInterrupt,
    onRejectPlan: session.handleRejectInterrupt,
    onOpenFile: (path: string, workspaceId?: string) => {
      if (assignmentId) return;
      const route = computeAgentArtifactRouting(path, workspaceId);
      setFile({ path: route.targetFile || path, workspaceId: route.setWorkspaceId || space.workspace_id });
    },
  }), [session.handleApproveCreateWorkspace, session.handleRejectCreateWorkspace, session.handleApproveStartQuestion,
    session.handleRejectStartQuestion, session.handleApprovePTCAgent, session.handleRejectPTCAgent,
    session.handleApproveSecretaryAction, session.handleRejectSecretaryAction, session.handleAnswerQuestion,
    session.handleSkipQuestion, session.handleApproveInterrupt, session.handleRejectInterrupt, handleRetry, space.workspace_id, assignmentId]);
  const reading = useBookReadingMutation(textbookId);
  const [message, setMessage] = useState('');
  const [voiceMode, setVoiceMode] = useState(false);
  const sending = session.isLoading;
  const blocked = sending || session.isLoadingHistory || Boolean(session.pendingInterrupt) || session.lessonBlocked;
  const turns = useMemo(() => questionTurns(session.messages), [session.messages]);
  const historyReady = !session.isLoadingHistory;
  const [viewportHeight, setViewportHeight] = useState(0);
  const submitGuard = useRef(false);
  const awaitingAnswer = useRef(false);
  const voiceHeld = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const turnRefs = useRef<Array<HTMLElement | null>>([]);
  const pendingScroll = useRef<number | null>(null);
  useScrollMemory(scrollRef, readingPositionKey ?? `lesson:${textbookId}:${assignmentId ?? ''}:${knowledgePointId}`, { persist: true, ready: historyReady });
  const { isListening, toggleListening, stopListening } = useVoiceInput({ message, setMessage, isLoading: sending });
  const markRef = useRef(reading.mutate);
  markRef.current = reading.mutate;

  useEffect(() => {
    if (!awaitingAnswer.current || session.isLoading || session.isLoadingHistory || session.pendingInterrupt || session.isReconnecting) return;
    const answer = session.messages.at(-1);
    if (answer?.role !== 'assistant' || answer.isStreaming) return;
    awaitingAnswer.current = false;
    if (!session.messageError && !answer.error && !answer.stopped && answer.content?.trim()) {
      markRef.current({ knowledgePointId, state: 'asked' });
    }
  }, [session.messages, session.isLoading, session.isLoadingHistory, session.pendingInterrupt, session.isReconnecting, session.messageError, knowledgePointId]);

  useEffect(() => {
    markRef.current({ knowledgePointId, state: 'viewed' });
  }, [knowledgePointId]);
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

  const submit = async (prompt?: string) => {
    const question = (prompt ?? message).trim();
    if (!question || submitGuard.current || blocked) return;
    submitGuard.current = true;
    awaitingAnswer.current = true;
    stopListening();
    setMessage('');
    const index = turns.length;
    pendingScroll.current = index;
    try {
      await session.handleSendMessage(question, false);
    } finally {
      submitGuard.current = false;
    }
  };
  sendPromptRef.current = (prompt) => void submit(prompt);
  return (
    <WorkspaceProvider workspaceId={assignmentId ? null : space.workspace_id} downloadFile={null}><MessageActionsProvider actions={actions}><div className="lesson-conversation">
      <div ref={scrollRef} className="lesson-conversation-scroll" role="region" aria-label="讲义与问答">
        <div className="lesson-original">{typeof children === 'function' ? children({ questionsBusy: sending || session.isLoadingHistory || session.isReconnecting || Boolean(session.messageError) }) : children}</div>
        {turns.map((turn, index) => <section key={index} ref={(node) => { turnRefs.current[index] = node; }} className="lesson-turn" aria-label={`第 ${index + 1} 轮问答`} style={index === turns.length - 1 ? { minHeight: viewportHeight } : undefined}>
          {turn.question && <div className="lesson-turn-question"><MessageBubble message={turn.question as unknown as Record<string, unknown>} turnIndex={index} isTurnTail={false} readOnly isMobile={isMobile} /></div>}
          <div className="lesson-turn-answer book-reader-prose">
            {turn.answers.map((answer) => <CitationMetadataProvider key={answer.id} toolCallProcesses={answer.toolCallProcesses as unknown as Record<string, Record<string, unknown>> ?? {}}>
              <MessageContentSegments {...(answer as unknown as ComponentProps<typeof MessageContentSegments>)} segments={answer.contentSegments ?? []}
                reasoningProcesses={answer.reasoningProcesses as unknown as Record<string, Record<string, unknown>> ?? {}}
                toolCallProcesses={answer.toolCallProcesses as unknown as Record<string, Record<string, unknown>> ?? {}}
                todoListProcesses={answer.todoListProcesses as unknown as Record<string, Record<string, unknown>> ?? {}}
                subagentTasks={answer.subagentTasks ?? {}} isStreaming={answer.isStreaming} hasError={Boolean(answer.error)}
                isAssistant textOnly readOnly={session.isLoadingHistory || session.isReconnecting} allowFiles={!assignmentId} renderText={renderLessonText}
                flashContext={{ threadId: space.conversation_thread_id, workspaceId: space.workspace_id }} />
            </CitationMetadataProvider>)}
            {(session.artifactReferences ?? []).filter((reference) => reference.assistantMessageId
              ? turn.answers.some((answer) => answer.id === reference.assistantMessageId)
              : reference.turnIndex === (turn.question?.role === 'user' ? turn.question.turnIndex ?? index : index)
                || turn.answers.some((answer) => answer.turnIndex === reference.turnIndex)).map((reference) => <div key={reference.key} className="my-2 text-sm">
              {assignmentId ? <p className="text-muted-foreground">此作品需要家长工作区权限</p> : <Button variant="outline" className="max-w-full h-auto whitespace-normal text-left" onClick={() => {
                if (reference.type === 'preview_url') void openPreview(reference);
                else actions.onOpenFile(String(reference.payload.file_path ?? ''), reference.payload.workspace_id as string | undefined);
              }}>
                {reference.type === 'preview_url' ? <Globe className="size-4 shrink-0" /> : <FileText className="size-4 shrink-0" />}
                <span className="break-all">{String(reference.payload.title ?? reference.payload.file_path ?? `预览 :${reference.payload.port}`)}</span>
              </Button>}
            </div>)}
            {sending && index === turns.length - 1 && <div className="flex items-center gap-2 text-xs text-muted-foreground" role="status"><Loader /><span>正在回答…</span></div>}
          </div>
        </section>)}
      </div>
      <footer className="lesson-composer">
        {session.pendingInterrupt && <p className="mb-2 text-xs text-muted-foreground" role="status">等待确认，请处理上方卡片</p>}
        {session.lessonBlocked && <p className="mb-2 text-xs text-muted-foreground" role="status">另一知识点的问答尚未结束，请先返回处理</p>}
        {session.awaitingReportBack && <p className="mb-2 text-xs text-muted-foreground" role="status">后台任务进行中</p>}
        {session.messageError && <div role="alert" className="flex items-center gap-3 text-sm text-destructive">
          <span>{typeof session.messageError === 'string' ? session.messageError : session.messageError.message}</span>
          <button disabled={sending || session.isLoadingHistory} onClick={session.reloadHistory}>恢复会话</button>
          <button disabled={blocked} onClick={() => void session.handleRetry()}>重试回答</button>
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
          </div> : <textarea aria-label="讲义问题" placeholder="这份讲义输入追问... Enter 发送，Shift+Enter 换行" value={message} disabled={blocked}
            onChange={(event) => setMessage(event.target.value)} rows={2}
            onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void submit(); } }} />}
          <Button variant="ghost" size="icon" className="size-9 shrink-0" aria-label="发送问题" title="发送问题" disabled={!message.trim() || blocked || isListening} onClick={() => void submit()}><Send className="size-4" /></Button>
        </div>
        {reading.isError && <p className="mt-1 text-xs text-destructive" role="status">学习状态保存失败</p>}
      </footer>
      <Dialog open={Boolean(file)} onOpenChange={(open) => { if (!open) setFile(null); }}>
        <DialogContent className="max-w-5xl h-[85dvh] p-0"><DialogTitle className="sr-only">文件预览</DialogTitle>
          {file && <Suspense fallback={<Loader />}><FilePanel workspaceId={file.workspaceId} targetFile={file.path} onClose={() => setFile(null)} singleFileMode readOnly /></Suspense>}
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(preview)} onOpenChange={(open) => { if (!open) { previewRequest.current++; setPreview(null); } }}>
        <DialogContent className="max-w-5xl h-[85dvh] p-0"><DialogTitle className="sr-only">动态预览</DialogTitle>
          {preview && <Suspense fallback={<Loader />}>{preview.error ? <div role="alert" className="p-6">预览暂不可用或没有访问权限。<Button variant="outline" onClick={() => void openPreview({ key: '', turnIndex: 0, type: 'preview_url', payload: { ...preview } })}>重试预览</Button></div> : <PreviewViewer {...preview} onClose={() => { previewRequest.current++; setPreview(null); }} onRefresh={() => void openPreview({ key: '', turnIndex: 0, type: 'preview_url', payload: { ...preview } })} />}</Suspense>}
        </DialogContent>
      </Dialog>
    </div></MessageActionsProvider></WorkspaceProvider>
  );
}
