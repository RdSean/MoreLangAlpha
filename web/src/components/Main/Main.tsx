import React, { Suspense } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import PageLoading from '@/components/PageLoading/PageLoading';
import { useIsMobile } from '@/hooks/useIsMobile';
import { useSyncUserLocale } from '@/hooks/useSyncUserLocale';
import { ContextOverflowPill } from '@/components/ui/ContextOverflowPill';
import StudentFlashChat from '@/pages/Education/StudentFlashChat';
import { routeChunks } from './routeChunks';

const Dashboard = React.lazy(routeChunks.dashboard);
const ChatAgent = React.lazy(routeChunks.chat);
const Documents = React.lazy(routeChunks.documents);
const Automations = React.lazy(routeChunks.automations);
const Education = React.lazy(routeChunks.education);
const CreateHomework = React.lazy(async () => ({ default: (await routeChunks.createHomework()).CreateHomeworkPage }));
const TextbookLibrary = React.lazy(routeChunks.textbookLibrary);
const TextbookDetail = React.lazy(routeChunks.textbookDetail);
const StudentLearning = React.lazy(routeChunks.studentLearning);
const Settings = React.lazy(routeChunks.settings);

function Main() {
  const location = useLocation();
  const isMobile = useIsMobile();
  useSyncUserLocale();
  // Key by top-level path segment so /chat sub-routes share a key (no re-animation)
  const pageKey = location.pathname.split('/')[1] || 'dashboard';

  const routes = (
    <Suspense fallback={<PageLoading variant="pane" />}>
      <Routes location={location}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/chat" element={<StudentFlashChat><ChatAgent /></StudentFlashChat>} />
        <Route path="/chat/t/:threadId/:taskId" element={<StudentFlashChat><ChatAgent /></StudentFlashChat>} />
        <Route path="/chat/t/:threadId" element={<StudentFlashChat><ChatAgent /></StudentFlashChat>} />
        <Route path="/chat/:workspaceId" element={<StudentFlashChat><ChatAgent /></StudentFlashChat>} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/automations" element={<Automations />} />
        <Route path="/education" element={<Education />} />
        <Route path="/education/tasks/new" element={<CreateHomework />} />
        <Route path="/education/textbooks" element={<TextbookLibrary />} />
        <Route path="/education/textbooks/:textbookId" element={<TextbookDetail />} />
        <Route path="/education/learn/:assignmentId/:chapterId?" element={<StudentLearning />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Suspense>
  );

  // On mobile, skip AnimatePresence — instant page switches feel snappier
  if (isMobile) {
    return (
      <div className="main" style={{ height: '100%' }}>
        {routes}
        <ContextOverflowPill />
      </div>
    );
  }

  return (
    <div className="main">
      <AnimatePresence mode="wait">
        <motion.div
          key={pageKey}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15, ease: 'easeInOut' }}
          style={{ height: '100%' }}
        >
          {routes}
        </motion.div>
      </AnimatePresence>
      <ContextOverflowPill />
    </div>
  );
}

export default Main;
