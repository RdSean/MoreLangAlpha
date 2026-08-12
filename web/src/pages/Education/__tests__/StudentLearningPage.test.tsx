import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import StudentLearningPage from '../StudentLearningPage';

const state = vi.hoisted(() => ({
  learning: null as Record<string, unknown> | null,
  chatSpace: { workspace_id: 'workspace-1', conversation_thread_id: 'thread-1' },
  answer: vi.fn(),
  progress: vi.fn(),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: { user_id: 'student-1', name: '学生', role: 'student' } }),
}));

vi.mock('../queries', () => ({
  useStudentLearning: () => ({ data: state.learning, isLoading: false }),
  useLearningChatSpace: () => ({ data: state.chatSpace, isLoading: false, isError: false }),
  useTextbookMutations: () => ({
    answer: { mutateAsync: state.answer, isPending: false },
    progress: { mutateAsync: state.progress, isPending: false },
  }),
}));

beforeEach(() => {
  state.learning = {
    assignment_id: 'assignment-1',
    textbook_title: '英语第二册',
    chapters: [{
      chapter_id: 'chapter-1',
      title: '导读',
      markdown: '# 导读\n\n完成阅读后做知识检查。',
      teaching_material: '# 学习目标\n\n- 完成知识检查。',
      progress_status: 'not_started',
      questions: [{
        question_id: 'question-1',
        prompt: '完成本章学习后，下一步应该做什么？',
        options: { A: '完成知识检查', B: '跳过所有材料' },
        knowledge_point: '学习证据',
      }],
    }],
  };
  state.answer.mockReset().mockResolvedValue({ is_correct: true });
  state.progress.mockReset().mockResolvedValue(undefined);
});

describe('StudentLearningPage', () => {
  it('renders the assigned chapter and submits a deterministic objective answer', async () => {
    render(
      <MemoryRouter initialEntries={['/education/learn/assignment-1/chapter-1']}>
        <Routes><Route path="/education/learn/:assignmentId/:chapterId" element={<StudentLearningPage />} /></Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '英语第二册' })).toBeInTheDocument();
    expect(screen.getByText('完成阅读后做知识检查。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '发布版本' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: 'A. 完成知识检查' }));
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    await waitFor(() => expect(state.answer).toHaveBeenCalledWith({
      assignmentId: 'assignment-1', questionId: 'question-1', selectedOption: 'A',
    }));
  });

  it('opens directory and knowledge checks in separate mobile panels', () => {
    render(
      <MemoryRouter initialEntries={['/education/learn/assignment-1/chapter-1']}>
        <Routes><Route path="/education/learn/:assignmentId/:chapterId" element={<StudentLearningPage />} /></Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '目录' }));
    expect(screen.getByRole('navigation', { name: '章节目录' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    fireEvent.click(screen.getByRole('button', { name: '知识检查' }));
    expect(screen.getByRole('heading', { name: '知识检查' })).toBeVisible();
  });
});
