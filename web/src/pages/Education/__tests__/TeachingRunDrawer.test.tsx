import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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

  it('shows autonomous milestone detail and a durable waiting state for a long run', () => {
    render(
      <TeachingRunDrawer
        open
        onOpenChange={() => undefined}
        job={{
          job_id: 'job-1',
          teaching_package_id: 'package-1',
          content_version_id: 'version-1',
          status: 'running',
          phase: 'practice_build',
          attempt_count: 1,
          completed_chapter_count: 2,
          total_chapter_count: 8,
          created_at: '2026-08-14T00:00:00Z',
          last_heartbeat_at: '2026-08-14T00:15:00Z',
          actions: ['cancel'],
          events: [{
            sequence: 4,
            phase: 'practice_build',
            chapter_id: 'chapter-2',
            asset_kind: 'practice',
            summary: 'Agent 已报告：第 2 章已完成练习构建',
            created_at: '2026-08-14T00:15:00Z',
          }],
          attempts: [{ attempt_id: 'attempt-1', root_run_id: 'root-1', status: 'running', started_at: '2026-08-14T00:00:00Z' }],
        }}
      />,
    );

    expect(screen.getByText('练习构建')).toBeVisible();
    expect(screen.getByText('正在等待 Agent/模型响应')).toBeVisible();
    expect(screen.getByText('最近持久心跳')).toBeVisible();
    expect(screen.getByText('Agent 已报告')).toBeVisible();
    expect(screen.getByText('练习资产')).toBeVisible();
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

  it('links model configuration guidance without exposing runtime details', () => {
    render(
      <MemoryRouter>
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
            error_message: '教材教学加工需要先配置模型服务，再继续运行。',
            events: [],
            attempts: [],
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: '配置模型服务' })).toHaveAttribute(
      'href',
      '/setup/method',
    );
    expect(screen.queryByText(/api[_ -]?key|deepseek|zai/i)).not.toBeInTheDocument();
  });
});
