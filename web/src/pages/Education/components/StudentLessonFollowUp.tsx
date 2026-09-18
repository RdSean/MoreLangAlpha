import { useState } from 'react';
import { Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { sendChatMessageStream } from '@/pages/ChatAgent/utils/api';
import { useLearningChatSpace } from '../queries';

export default function StudentLessonFollowUp({
  assignmentId,
  knowledgePointId,
}: {
  assignmentId: string;
  knowledgePointId: string;
}) {
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
        { assignmentId, knowledgePointId },
      );
      setMessage('');
    } catch {
      setError('暂时无法发送问题，请稍后重试。');
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="border-t pt-6" style={{ borderColor: 'var(--color-border-muted)' }}>
      <h2 className="text-sm font-semibold">继续追问</h2>
      <p className="mt-1 text-sm text-muted-foreground">回答只依据当前已发布知识点课程。</p>
      <label className="sr-only" htmlFor="knowledge-point-question">问题</label>
      <textarea
        id="knowledge-point-question"
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        className="mt-4 min-h-24 w-full resize-y border bg-background p-3 text-sm"
        placeholder="围绕这个知识点提问"
      />
      <div className="mt-3 flex justify-end">
        <Button size="sm" onClick={() => void submit()} disabled={!message.trim() || sending || !chatSpace.data}>
          <Send className="mr-2 size-4" />{sending ? '正在回答' : '提问'}
        </Button>
      </div>
      {error && <p className="mt-3 text-sm" role="alert" style={{ color: 'var(--color-loss)' }}>{error}</p>}
      {answer && <div className="mt-4 border-l-2 pl-4 text-sm leading-6" style={{ borderColor: 'var(--color-border-muted)', color: 'var(--color-text-secondary)' }}>{answer}</div>}
    </section>
  );
}
