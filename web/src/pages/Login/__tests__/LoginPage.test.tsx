import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

const auth = {
  login: vi.fn(),
  registerParent: vi.fn(),
};

vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => auth }));

const { default: LoginPage } = await import('../LoginPage');

describe('LoginPage', () => {
  it('submits a local email or username login', async () => {
    const user = userEvent.setup();
    auth.login.mockResolvedValue(undefined);
    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    await user.type(screen.getByLabelText('登录标识'), 'parent@example.test');
    await user.type(screen.getByLabelText('密码'), 'a-long-enough-password');
    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(auth.login).toHaveBeenCalledWith('parent@example.test', 'a-long-enough-password');
  });

  it('collects parent and household information before registration', async () => {
    const user = userEvent.setup();
    auth.registerParent.mockResolvedValue(undefined);
    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    await user.click(screen.getByRole('button', { name: '创建家庭账户' }));
    await user.type(screen.getByLabelText('家长姓名'), 'Parent');
    await user.type(screen.getByLabelText('邮箱'), 'parent@example.test');
    await user.type(screen.getByLabelText('家庭名称'), 'Lee family');
    await user.type(screen.getByLabelText('设置密码'), 'a-long-enough-password');
    await user.type(screen.getByLabelText('确认密码'), 'a-long-enough-password');
    await user.click(screen.getByRole('button', { name: '创建账户' }));

    expect(auth.registerParent).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Parent',
      email: 'parent@example.test',
      householdName: 'Lee family',
      password: 'a-long-enough-password',
    }));
  });
});
