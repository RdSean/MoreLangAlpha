import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import ProcessingProfileDialog from '../components/ProcessingProfileDialog';

describe('ProcessingProfileDialog', () => {
  it('collects bounded textbook processing settings', async () => {
    const user = userEvent.setup();
    const confirm = vi.fn().mockResolvedValue(undefined);
    render(
      <ProcessingProfileDialog
        open
        onOpenChange={vi.fn()}
        onConfirm={confirm}
      />,
    );

    await user.selectOptions(screen.getByLabelText('学科'), 'math');
    await user.selectOptions(screen.getByLabelText('学段'), 'high');
    await user.selectOptions(screen.getByLabelText('讲解深度'), 'deep');
    await user.click(screen.getByLabelText('填空'));
    await user.type(screen.getByLabelText('补充要求'), '强调解题步骤');
    await user.click(screen.getByRole('button', { name: '开始结构分析' }));

    await waitFor(() => expect(confirm).toHaveBeenCalledWith(expect.objectContaining({
      subject: 'math',
      grade_band: 'high',
      depth: 'deep',
      question_types: expect.arrayContaining(['fill']),
      prompt_fragment: '强调解题步骤',
    })));
  });
});
