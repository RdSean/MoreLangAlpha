import { useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import PageLoading from '@/components/PageLoading/PageLoading';
import { useAuth } from '@/contexts/AuthContext';
import { ensureStudentFlashWorkspace } from './api';

export default function StudentFlashChat({ children }: { children: React.ReactNode }) {
  const { member } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const started = useRef(false);
  const isRootChatRoute = pathname === '/chat';

  useEffect(() => {
    if (member?.role !== 'student' || !isRootChatRoute || started.current) return;
    started.current = true;
    void ensureStudentFlashWorkspace()
      .then((workspace) => navigate(`/chat/${workspace.workspace_id}`, { replace: true }))
      .catch(() => navigate('/education', { replace: true }));
  }, [isRootChatRoute, member?.role, navigate]);

  if (member?.role === 'student' && isRootChatRoute) return <PageLoading variant="pane" />;
  return <>{children}</>;
}
