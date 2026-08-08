import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import PageLoading from '@/components/PageLoading/PageLoading';
import { useAuth } from '@/contexts/AuthContext';
import { ensureStudentFlashWorkspace } from './api';

export default function StudentFlashChat({ children }: { children: React.ReactNode }) {
  const { member } = useAuth();
  const navigate = useNavigate();
  const started = useRef(false);

  useEffect(() => {
    if (member?.role !== 'student' || started.current) return;
    started.current = true;
    void ensureStudentFlashWorkspace()
      .then((workspace) => navigate(`/chat/${workspace.workspace_id}`, { replace: true }))
      .catch(() => navigate('/education', { replace: true }));
  }, [member?.role, navigate]);

  if (member?.role === 'student') return <PageLoading variant="pane" />;
  return <>{children}</>;
}
