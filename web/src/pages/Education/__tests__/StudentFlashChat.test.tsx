import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  member: { user_id: 'student-1', name: 'Student', role: 'student' as 'parent' | 'student' },
  ensureFlashWorkspace: vi.fn(),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ member: state.member }),
}));

vi.mock('../api', () => ({
  ensureStudentFlashWorkspace: state.ensureFlashWorkspace,
}));

import StudentFlashChat from '../StudentFlashChat';

function CurrentPath() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

function renderStudentFlashChat(initialEntry: string) {
  return render(
    <MemoryRouter
      initialEntries={[initialEntry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route
          path="/chat/*"
          element={<StudentFlashChat><div data-testid="student-chat">Student Flash chat</div></StudentFlashChat>}
        />
      </Routes>
      <CurrentPath />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  state.member = { user_id: 'student-1', name: 'Student', role: 'student' };
  state.ensureFlashWorkspace.mockReset().mockResolvedValue({
    workspace_id: '11111111-1111-4111-8111-111111111111',
  });
});

describe('StudentFlashChat', () => {
  it('redirects a student from the root chat route to their Flash workspace and renders the chat', async () => {
    renderStudentFlashChat('/chat');

    expect(document.querySelector('.page-loading')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByTestId('student-chat')).toBeInTheDocument());

    expect(state.ensureFlashWorkspace).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('location')).toHaveTextContent('/chat/11111111-1111-4111-8111-111111111111');
  });

  it('renders a student thread deep link without ensuring another Flash workspace', () => {
    renderStudentFlashChat('/chat/t/22222222-2222-4222-8222-222222222222');

    expect(screen.getByTestId('student-chat')).toBeInTheDocument();
    expect(state.ensureFlashWorkspace).not.toHaveBeenCalled();
  });
});
