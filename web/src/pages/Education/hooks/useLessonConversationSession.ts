import { useCallback, useMemo, useRef, useState } from 'react';
import { useChatMessages } from '@/pages/ChatAgent/hooks/useChatMessages';
import type { PreviewData } from '@/pages/ChatAgent/hooks/utils/types';
import { replayLessonConversation, getLessonConversationStatus } from '../api';
import type { LearningChatSpace } from '../types';

export interface LessonArtifactReference {
  key: string;
  turnIndex: number;
  assistantMessageId?: string;
  type: 'file_operation' | 'preview_url';
  payload: Record<string, unknown>;
}

export function useLessonConversationSession(space: LearningChatSpace, textbookId: string, knowledgePointId: string, assignmentId?: string) {
  const [lessonBlocked, setLessonBlocked] = useState(false);
  const [artifactReferences, setArtifactReferences] = useState<LessonArtifactReference[]>([]);
  const latestTurn = useRef(0);
  const rememberArtifact = useCallback((event: Record<string, unknown>, assistantMessageId?: string) => {
    if (event.artifact_type !== 'file_operation' && event.artifact_type !== 'preview_url') return;
    const payload = (event.payload ?? {}) as Record<string, unknown>;
    const key = String(event.artifact_id ?? `${event.artifact_type}:${payload.file_path ?? payload.port}`);
    const reference: LessonArtifactReference = { key, type: event.artifact_type, payload, assistantMessageId,
      turnIndex: typeof event.turn_index === 'number' ? event.turn_index : latestTurn.current };
    setArtifactReferences((previous) => [...previous.filter((item) => item.key !== key), reference]);
  }, []);
  const rememberPreview = useCallback((data: PreviewData, assistantMessageId?: string) => rememberArtifact({
    artifact_type: 'preview_url', artifact_id: data.artifactId, payload: data,
  }, assistantMessageId), [rememberArtifact]);
  const options = useMemo(() => ({
    educationContext: assignmentId ? { assignmentId, knowledgePointId } : { textbookId, knowledgePointId },
    readWorkflowStatus: async (threadId: string) => {
      if (threadId !== space.conversation_thread_id) throw new Error('Learning conversation changed');
      const status = await getLessonConversationStatus(textbookId, knowledgePointId, assignmentId);
      setLessonBlocked(Boolean(status.lesson_blocked));
      return status;
    },
    replayHistory: async (threadId: string, onEvent: (event: Record<string, unknown>) => void) => {
      if (threadId !== space.conversation_thread_id) throw new Error('Learning conversation changed');
      setArtifactReferences([]);
      latestTurn.current = 0;
      await replayLessonConversation(textbookId, knowledgePointId, assignmentId, (event) => {
        if (typeof event.turn_index === 'number') latestTurn.current = event.turn_index;
        if (event.event === 'artifact') rememberArtifact(event);
        onEvent(event);
      });
    },
  }), [space.conversation_thread_id, textbookId, knowledgePointId, assignmentId, rememberArtifact]);
  const session = useChatMessages(space.workspace_id, space.conversation_thread_id, null, null, null, rememberArtifact, rememberPreview,
    'flash', null, null, null, options);
  return { ...session, lessonBlocked, artifactReferences };
}
