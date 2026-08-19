import { FormEvent, useState } from 'react';
import { MessageSquarePlus, Plus, UserRound } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useCreateChildAccount, useFamilyChildren } from '../queries';

interface FamilyAccountsTabProps {
  onOpenChild: (studentUserId: string) => void;
}

function apiErrorMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 409) return '该用户名已被使用，请更换后重试。';
  if (status === 422) return '请检查用户名、姓名和初始密码。';
  return '创建账户失败，请稍后重试。';
}

export function FamilyAccountsTab({ onOpenChild }: FamilyAccountsTabProps) {
  const { member } = useAuth();
  const isParent = member?.role === 'parent';
  const childrenQuery = useFamilyChildren(isParent);
  const createChild = useCreateChildAccount();
  const [isDialogOpen, setDialogOpen] = useState(false);
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (!isParent) {
    return <p className="py-8 text-sm" style={{ color: 'var(--color-text-secondary)' }}>只有家长可以管理家庭账户。</p>;
  }

  const closeDialog = (open: boolean) => {
    setDialogOpen(open);
    if (!open) setError(null);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      await createChild.mutateAsync({ username: username.trim(), name: name.trim(), password });
      setUsername('');
      setName('');
      setPassword('');
      setDialogOpen(false);
    } catch (submitError) {
      setError(apiErrorMessage(submitError));
    }
  };

  return <section className="space-y-6" aria-labelledby="family-accounts-heading">
    <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between" style={{ borderColor: 'var(--color-border-muted)' }}>
      <div>
        <h3 id="family-accounts-heading" className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>家庭账户</h3>
        <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>管理子女账户，并查看其私有 Flash 空间的对话记录。</p>
      </div>
      <Dialog open={isDialogOpen} onOpenChange={closeDialog}>
        <DialogTrigger asChild><Button><Plus className="mr-2 size-4" aria-hidden="true" />添加子女账户</Button></DialogTrigger>
        <DialogContent variant="centered" className="max-w-md">
          <DialogHeader>
            <DialogTitle>添加子女账户</DialogTitle>
            <DialogDescription>子女仅可使用自己的 Flash 空间和家庭学习功能。</DialogDescription>
          </DialogHeader>
          <form className="grid gap-4" onSubmit={(event) => void submit(event)}>
            <label className="grid gap-1.5 text-sm font-medium" htmlFor="child-username">用户名<Input id="child-username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required minLength={3} maxLength={64} /></label>
            <p className="-mt-2 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>仅小写字母、数字、点、短横线或下划线。</p>
            <label className="grid gap-1.5 text-sm font-medium" htmlFor="child-name">姓名<Input id="child-name" value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" required maxLength={255} /></label>
            <label className="grid gap-1.5 text-sm font-medium" htmlFor="child-password">初始密码<Input id="child-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required minLength={12} /></label>
            <p className="-mt-2 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>至少 12 个字符。</p>
            {error && <p role="alert" className="text-sm" style={{ color: 'var(--color-loss)' }}>{error}</p>}
            <DialogFooter><Button type="submit" disabled={createChild.isPending}>{createChild.isPending ? '正在创建' : '创建账户'}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </header>

    {childrenQuery.isLoading && <p className="py-8 text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在加载家庭账户…</p>}
    {childrenQuery.isError && <div className="py-8"><p className="text-sm" style={{ color: 'var(--color-loss)' }}>无法加载家庭账户。</p><Button className="mt-3" size="sm" variant="outline" onClick={() => void childrenQuery.refetch()}>重试</Button></div>}
    {!childrenQuery.isLoading && !childrenQuery.isError && (childrenQuery.data ?? []).length === 0 && <p className="py-8 text-sm" style={{ color: 'var(--color-text-secondary)' }}>暂未添加子女账户。</p>}
    {!childrenQuery.isLoading && !childrenQuery.isError && <div className="divide-y" style={{ borderColor: 'var(--color-border-muted)' }}>
      {(childrenQuery.data ?? []).map((child) => <article key={child.user_id} className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-md" style={{ backgroundColor: 'var(--color-accent-soft)', color: 'var(--color-accent-primary)' }}><UserRound className="size-4" aria-hidden="true" /></span>
          <div className="min-w-0"><h4 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{child.name}</h4><p className="mt-0.5 font-mono text-xs" style={{ color: 'var(--color-text-tertiary)' }}>{child.username}</p><p className="mt-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>Flash 空间：{child.flash_workspace.status === 'flash' ? '可用' : child.flash_workspace.status ?? '未知'}</p></div>
        </div>
        <Button size="sm" variant="outline" onClick={() => onOpenChild(child.user_id)}><MessageSquarePlus className="mr-2 size-4" aria-hidden="true" />查看对话</Button>
      </article>)}
    </div>}
  </section>;
}
