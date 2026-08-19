import { useCallback, useRef, useState } from 'react';
import { ArrowLeft, MessageSquareText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { streamFamilyChildThreadReplay, type FamilyThread } from '../api';
import { useFamilyChildThreads, useFamilyChildWorkspace } from '../queries';

interface FamilyChildConversationsProps {
  student: { user_id: string; name: string };
  onBack: () => void;
}

interface TranscriptMessage {
  role: 'user' | 'assistant';
  content: string;
}

function appendReplayEvent(messages: TranscriptMessage[], event: Record<string, unknown>): TranscriptMessage[] {
  if (event.event === 'user_message' && typeof event.content === 'string') {
    return [...messages, { role: 'user', content: event.content }];
  }
  if (event.event === 'message_chunk' && event.role === 'assistant' && typeof event.content === 'string') {
    const previous = messages.at(-1);
    if (previous?.role === 'assistant') {
      return [...messages.slice(0, -1), { ...previous, content: previous.content + event.content }];
    }
    return [...messages, { role: 'assistant', content: event.content }];
  }
  return messages;
}

function workspaceStatus(status: unknown): string {
  return status === 'flash' ? '可用' : typeof status === 'string' ? status : '未知';
}

export function FamilyChildConversations({ student, onBack }: FamilyChildConversationsProps) {
  const workspaceQuery = useFamilyChildWorkspace(student.user_id);
  const threadsQuery = useFamilyChildThreads(student.user_id);
  const [selectedThread, setSelectedThread] = useState<FamilyThread | null>(null);
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [isTranscriptLoading, setTranscriptLoading] = useState(false);
  const [transcriptError, setTranscriptError] = useState(false);
  const requestVersion = useRef(0);

  const loadTranscript = useCallback(async (thread: FamilyThread) => {
    const version = ++requestVersion.current;
    setSelectedThread(thread);
    setMessages([]);
    setTranscriptError(false);
    setTranscriptLoading(true);
    try {
      await streamFamilyChildThreadReplay(student.user_id, thread.thread_id, (event) => {
        if (version !== requestVersion.current) return;
        setMessages((current) => appendReplayEvent(current, event));
      });
    } catch {
      if (version === requestVersion.current) setTranscriptError(true);
    } finally {
      if (version === requestVersion.current) setTranscriptLoading(false);
    }
  }, [student.user_id]);

  return <section className="space-y-6" aria-labelledby="family-child-conversations-heading">
    <header className="border-b pb-5" style={{ borderColor: 'var(--color-border-muted)' }}>
      <Button size="sm" variant="ghost" className="-ml-3" onClick={onBack}><ArrowLeft className="mr-2 size-4" aria-hidden="true" />返回家庭账户</Button>
      <h3 id="family-child-conversations-heading" className="mt-4 text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>{student.name}的对话记录</h3>
      {workspaceQuery.isLoading && <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在读取 Flash 空间状态…</p>}
      {workspaceQuery.isError && <div className="mt-2"><p className="text-sm" style={{ color: 'var(--color-loss)' }}>无法读取 Flash 空间状态。</p><Button className="mt-2" size="sm" variant="outline" onClick={() => void workspaceQuery.refetch()}>重试</Button></div>}
      {workspaceQuery.data && <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>Flash 空间状态：{workspaceStatus(workspaceQuery.data.status)}</p>}
    </header>

    <div className="grid gap-6 lg:grid-cols-[minmax(200px,0.38fr)_minmax(0,1fr)]">
      <section aria-label="对话列表" className="min-w-0">
        <h4 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>对话</h4>
        {threadsQuery.isLoading && <p className="py-5 text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在加载对话…</p>}
        {threadsQuery.isError && <div className="py-5"><p className="text-sm" style={{ color: 'var(--color-loss)' }}>无法加载对话记录。</p><Button className="mt-2" size="sm" variant="outline" onClick={() => void threadsQuery.refetch()}>重试</Button></div>}
        {!threadsQuery.isLoading && !threadsQuery.isError && (threadsQuery.data?.threads ?? []).length === 0 && <p className="py-5 text-sm" style={{ color: 'var(--color-text-secondary)' }}>该 Flash 空间暂无对话记录。</p>}
        <div className="mt-3 divide-y border-y" style={{ borderColor: 'var(--color-border-muted)' }}>
          {(threadsQuery.data?.threads ?? []).map((thread) => <button key={thread.thread_id} type="button" onClick={() => void loadTranscript(thread)} className="block w-full px-3 py-3 text-left hover:bg-[var(--color-bg-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-current={selectedThread?.thread_id === thread.thread_id ? 'page' : undefined}>
            <span className="block truncate text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>{thread.title || thread.first_query_content || '未命名对话'}</span>
            {thread.updated_at && <span className="mt-1 block text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{new Date(thread.updated_at).toLocaleString()}</span>}
          </button>)}
        </div>
      </section>

      <section aria-label="只读对话内容" className="min-w-0 border-t pt-5 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0" style={{ borderColor: 'var(--color-border-muted)' }}>
        {!selectedThread && <div className="flex min-h-48 flex-col items-center justify-center text-center"><MessageSquareText className="size-5" aria-hidden="true" style={{ color: 'var(--color-text-tertiary)' }} /><p className="mt-3 text-sm" style={{ color: 'var(--color-text-secondary)' }}>选择一段对话以查看记录。</p></div>}
        {selectedThread && <>
          <h4 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{selectedThread.title || selectedThread.first_query_content || '未命名对话'}</h4>
          {isTranscriptLoading && <p className="mt-4 text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在加载对话内容…</p>}
          {transcriptError && <div className="mt-4"><p className="text-sm" style={{ color: 'var(--color-loss)' }}>无法加载这段对话。</p><Button className="mt-2" size="sm" variant="outline" onClick={() => void loadTranscript(selectedThread)}>重试</Button></div>}
          {!isTranscriptLoading && !transcriptError && messages.length === 0 && <p className="mt-4 text-sm" style={{ color: 'var(--color-text-secondary)' }}>这段对话没有可显示的文本内容。</p>}
          <div className="mt-4 space-y-3">
            {messages.map((message, index) => <article key={`${message.role}-${index}`} className="border-l-2 pl-3" style={{ borderColor: message.role === 'user' ? 'var(--color-accent-primary)' : 'var(--color-border-default)' }}>
              <p className="text-xs font-medium" style={{ color: 'var(--color-text-tertiary)' }}>{message.role === 'user' ? student.name : '助手'}</p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-6" style={{ color: 'var(--color-text-primary)' }}>{message.content}</p>
            </article>)}
          </div>
        </>}
      </section>
    </div>
  </section>;
}
