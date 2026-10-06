import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { BookReader } from '../components/BookReader';
import { BookLearningStart } from '../components/BookLearningStart';

const missingMaterial = { textbook_id: 'book', knowledge_point_id: 'kp', skill_kp_id: 'skill', material_available: false, markdown: null, generated_at: null, depth: null, requirements: null, content_sha256: null };

describe('BookLearningStart', () => {
  it.each([['简洁', 'summary'], ['标准', 'lesson'], ['深入', 'deep']])('starts %s with the matching depth', async (label, depth) => {
    const user = userEvent.setup();
    const onStart = vi.fn();
    render(<BookLearningStart onStart={onStart} />);
    await user.click(screen.getByRole('button', { name: '选择讲解模式' }));
    await user.click(screen.getByRole('menuitem', { name: new RegExp(label) }));
    expect(onStart).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '开始学习' }));
    expect(onStart).toHaveBeenCalledWith({ depth, requirements: null, replaceExisting: false, includeSupplementary: false });
  });

  it('expands custom settings in place and submits the chosen depth and trimmed requirements', async () => {
    const user = userEvent.setup();
    const onStart = vi.fn();
    render(<BookLearningStart onStart={onStart} />);
    expect(screen.queryByLabelText('补充要求（可选）')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '选择讲解模式' }));
    await user.click(screen.getByRole('menuitem', { name: /自定义/ }));
    expect(onStart).not.toHaveBeenCalled();
    await user.selectOptions(screen.getByLabelText('讲解深度'), 'deep');
    await user.type(screen.getByLabelText('补充要求（可选）'), '  多给两个例子  ');
    await user.click(screen.getByRole('button', { name: '开始学习' }));
    expect(onStart).toHaveBeenCalledWith({ depth: 'deep', requirements: '多给两个例子', replaceExisting: false, includeSupplementary: false });
  });

  it('shows no generation action without parent permission', () => {
    render(<BookLearningStart />);
    expect(screen.queryByRole('button', { name: '开始学习' })).not.toBeInTheDocument();
    expect(screen.getByText('等待家长准备课程')).toBeInTheDocument();
  });

  it('disables starting and mode changes while a job is pending', () => {
    render(<BookLearningStart onStart={vi.fn()} pending />);
    expect(screen.getByRole('button', { name: '正在准备课程' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '选择讲解模式' })).toBeDisabled();
  });

  it('keeps a missing lecture learning screen separate from source Markdown', () => {
    render(<BookReader title="足球" view="source" learningView canManageMaterials
      material={missingMaterial}
      source={{ textbook_id: 'book', start_line: 1, end_line: 2, total_lines: 2, markdown: 'Source should not appear.' }}
      onViewChange={vi.fn()} onGenerate={vi.fn()} />);
    expect(screen.getByRole('button', { name: '开始学习' })).toBeInTheDocument();
    expect(screen.queryByText('Source should not appear.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '生成讲义' })).not.toBeInTheDocument();
  });

  it('keeps custom inputs after a failed start and allows retry', async () => {
    const user = userEvent.setup();
    const onGenerate = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined);
    render(<BookReader title="足球" view="source" learningView canManageMaterials
      material={missingMaterial} onViewChange={vi.fn()} onGenerate={onGenerate} />);
    await user.click(screen.getByRole('button', { name: '选择讲解模式' }));
    await user.click(screen.getByRole('menuitem', { name: /自定义/ }));
    await user.type(screen.getByLabelText('补充要求（可选）'), '增加例题');
    await user.click(screen.getByRole('button', { name: '开始学习' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('课程暂时未能开始');
    expect(screen.getByLabelText('补充要求（可选）')).toHaveValue('增加例题');
    await user.click(screen.getByRole('button', { name: '开始学习' }));
    expect(onGenerate).toHaveBeenCalledTimes(2);
    expect(onGenerate).toHaveBeenLastCalledWith(expect.objectContaining({ requirements: '增加例题', replaceExisting: false }));
  });
});
