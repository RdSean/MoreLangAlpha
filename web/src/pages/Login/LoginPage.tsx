import React, { useState } from 'react';
import { ArrowLeft, LogIn, UsersRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/contexts/AuthContext';

type View = 'login' | 'register';

function authErrorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : '无法完成请求，请检查输入后重试。';
}

function LoginPage() {
  const { login, registerParent } = useAuth();
  const [view, setView] = useState<View>('login');
  const [loginIdentifier, setLoginIdentifier] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [householdName, setHouseholdName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const switchView = (next: View) => {
    setError(null);
    setView(next);
  };

  const submitLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      await login(loginIdentifier.trim(), loginPassword);
    } catch (reason) {
      setError(authErrorMessage(reason));
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitRegistration = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (password.length < 12) {
      setError('密码至少需要 12 个字符。');
      return;
    }
    if (password !== confirmation) {
      setError('两次输入的密码不一致。');
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await registerParent({
        email: email.trim(),
        password,
        name: name.trim(),
        householdName: householdName.trim(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
      });
    } catch (reason) {
      setError(authErrorMessage(reason));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-dvh bg-page px-4 py-8 text-foreground sm:px-6 lg:px-8">
      <section className="mx-auto flex min-h-[calc(100dvh-4rem)] w-full max-w-md items-center">
        <div className="w-full rounded-lg border border-border bg-card p-6 shadow-[var(--shadow-card)] sm:p-8">
          <div className="mb-8">
            <p className="font-mono text-xs text-muted-foreground">LANGALPHA</p>
            <h1 className="title-font mt-3 text-2xl font-semibold">{view === 'login' ? '登录工作区' : '创建家庭账户'}</h1>
          </div>

          {view === 'login' ? (
            <form className="space-y-5" onSubmit={submitLogin}>
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="login-identifier">登录标识</label>
                <Input
                  id="login-identifier"
                  autoComplete="username"
                  value={loginIdentifier}
                  onChange={(event) => setLoginIdentifier(event.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="login-password">密码</label>
                <Input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  value={loginPassword}
                  onChange={(event) => setLoginPassword(event.target.value)}
                  required
                />
              </div>
              {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
              <Button className="w-full" disabled={isSubmitting} type="submit">
                <LogIn aria-hidden="true" className="mr-2 size-4" />
                {isSubmitting ? '正在登录' : '登录'}
              </Button>
              <Button className="w-full" variant="outline" type="button" onClick={() => switchView('register')}>
                <UsersRound aria-hidden="true" className="mr-2 size-4" />
                创建家庭账户
              </Button>
            </form>
          ) : (
            <form className="space-y-5" onSubmit={submitRegistration}>
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="parent-name">家长姓名</label>
                <Input id="parent-name" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} required />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="parent-email">邮箱</label>
                <Input id="parent-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="household-name">家庭名称</label>
                <Input id="household-name" value={householdName} onChange={(event) => setHouseholdName(event.target.value)} required />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="register-password">设置密码</label>
                <Input id="register-password" type="password" minLength={12} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="register-confirmation">确认密码</label>
                <Input id="register-confirmation" type="password" minLength={12} autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required />
              </div>
              {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
              <Button className="w-full" disabled={isSubmitting} type="submit">
                <UsersRound aria-hidden="true" className="mr-2 size-4" />
                {isSubmitting ? '正在创建' : '创建账户'}
              </Button>
              <Button className="w-full" variant="ghost" type="button" onClick={() => switchView('login')}>
                <ArrowLeft aria-hidden="true" className="mr-2 size-4" />
                返回登录
              </Button>
            </form>
          )}
        </div>
      </section>
    </main>
  );
}

export default LoginPage;
