import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import TeachingRunDrawer from '../TeachingRunDrawer';

describe('TeachingRunDrawer', () => {
  it('projects a managed PTC attempt without a chat composer', () => {
    render(
      <TeachingRunDrawer
        open
        onOpenChange={() => undefined}
        job={{
          job_id: 'job-1',
          teaching_package_id: 'package-1',
          content_version_id: 'version-1',
          status: 'running',
          phase: 'generating_teaching',
          attempt_count: 1,
          completed_chapter_count: 2,
          total_chapter_count: 8,
          actions: ['cancel'],
          events: [{ sequence: 2, phase: 'generating_teaching', summary: '已完成第 2 章教学材料生成' }],
          attempts: [{ attempt_id: 'attempt-1', root_run_id: 'root-1', status: 'running' }],
        }}
      />,
    );

    expect(screen.getByText('生成教学材料')).toBeVisible();
    expect(screen.getByText('已完成 2 / 8 章')).toBeVisible();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('does not render unsafe server runtime data even if a fixture contains it', () => {
    render(
      <TeachingRunDrawer
        open
        onOpenChange={() => undefined}
        job={{
          job_id: 'job-1',
          teaching_package_id: 'package-1',
          content_version_id: 'version-1',
          status: 'failed',
          phase: 'failed',
          attempt_count: 1,
          completed_chapter_count: 0,
          total_chapter_count: 1,
          actions: ['resume'],
          events: [],
          attempts: [],
          storage_key: 'education/private/source.pdf',
          managed_path: '/managed/textbook-job/private',
          minio_url: 'http://minio.invalid/private',
        } as never}
      />,
    );

    expect(screen.queryByText(/storage_key|\/managed\/|minio/i)).not.toBeInTheDocument();
  });
});
