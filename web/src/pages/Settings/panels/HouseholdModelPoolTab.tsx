import { type FormEvent, useState } from 'react';
import { Check, KeyRound, Pencil, Plus, Power, Star, Trash2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { FamilyLlmEndpoint, FamilyLlmEndpointInput, FamilyLlmEndpointUpdate } from '../api';
import {
  useCreateFamilyLlmEndpoint,
  useDeleteFamilyLlmEndpoint,
  useFamilyLlmPool,
  useSetFamilyLlmDefault,
  useUpdateFamilyLlmEndpoint,
} from '../queries';

interface EndpointFormState {
  displayName: string;
  provider: string;
  modelId: string;
  baseUrl: string;
  apiKey: string;
  clearApiKey: boolean;
  enabled: boolean;
  sortOrder: number;
}

const EMPTY_FORM: EndpointFormState = {
  displayName: '',
  provider: '',
  modelId: '',
  baseUrl: '',
  apiKey: '',
  clearApiKey: false,
  enabled: true,
  sortOrder: 0,
};

function endpointForm(endpoint: FamilyLlmEndpoint): EndpointFormState {
  return {
    displayName: endpoint.display_name,
    provider: endpoint.provider,
    modelId: endpoint.model_id,
    baseUrl: endpoint.base_url ?? '',
    apiKey: '',
    clearApiKey: false,
    enabled: endpoint.enabled,
    sortOrder: endpoint.sort_order,
  };
}

function errorMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 409) return '该模型当前无法作为默认模型，请刷新后重试。';
  if (status === 422) return '请检查模型配置后重试。';
  return '保存失败，请稍后重试。';
}

export function HouseholdModelPoolTab() {
  const { member } = useAuth();
  const isParent = member?.role === 'parent';
  const poolQuery = useFamilyLlmPool(isParent);
  const createEndpoint = useCreateFamilyLlmEndpoint();
  const updateEndpoint = useUpdateFamilyLlmEndpoint();
  const deleteEndpoint = useDeleteFamilyLlmEndpoint();
  const setDefault = useSetFamilyLlmDefault();

  const [editing, setEditing] = useState<FamilyLlmEndpoint | null>(null);
  const [form, setForm] = useState<EndpointFormState>(EMPTY_FORM);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FamilyLlmEndpoint | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!isParent) return null;

  const endpoints = poolQuery.data?.endpoints ?? [];
  const defaultEndpointId = poolQuery.data?.default_endpoint_id ?? null;
  const enabledEndpoints = endpoints.filter((endpoint) => endpoint.enabled);
  const isSaving = createEndpoint.isPending || updateEndpoint.isPending;

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setDialogOpen(true);
  };

  const openEdit = (endpoint: FamilyLlmEndpoint) => {
    setEditing(endpoint);
    setForm(endpointForm(endpoint));
    setFormError(null);
    setDialogOpen(true);
  };

  const closeDialog = (open: boolean) => {
    setDialogOpen(open);
    if (!open) setFormError(null);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);
    const base = {
      display_name: form.displayName.trim(),
      provider: form.provider.trim(),
      model_id: form.modelId.trim(),
      base_url: form.baseUrl.trim() || null,
      enabled: form.enabled,
      sort_order: form.sortOrder,
    };

    try {
      if (editing) {
        const update: FamilyLlmEndpointUpdate = {
          ...base,
          ...(form.clearApiKey ? { api_key: '' } : form.apiKey ? { api_key: form.apiKey } : {}),
        };
        await updateEndpoint.mutateAsync({ endpointId: editing.endpoint_id, input: update });
      } else {
        const create: FamilyLlmEndpointInput = {
          ...base,
          ...(form.apiKey ? { api_key: form.apiKey } : {}),
        };
        await createEndpoint.mutateAsync(create);
      }
      setDialogOpen(false);
    } catch (error) {
      setFormError(errorMessage(error));
    }
  };

  const updateEnabled = async (endpoint: FamilyLlmEndpoint) => {
    setActionError(null);
    try {
      await updateEndpoint.mutateAsync({
        endpointId: endpoint.endpoint_id,
        input: { enabled: !endpoint.enabled },
      });
    } catch (error) {
      setActionError(errorMessage(error));
    }
  };

  const updateDefault = async (endpointId: string | null) => {
    setActionError(null);
    try {
      await setDefault.mutateAsync(endpointId);
    } catch (error) {
      setActionError(errorMessage(error));
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setActionError(null);
    try {
      await deleteEndpoint.mutateAsync(deleteTarget.endpoint_id);
      setDeleteTarget(null);
    } catch (error) {
      setActionError(errorMessage(error));
      throw error;
    }
  };

  return (
    <section className="space-y-6" aria-labelledby="household-model-pool-heading">
      <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-end sm:justify-between" style={{ borderColor: 'var(--color-border-muted)' }}>
        <div>
          <h3 id="household-model-pool-heading" className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>家庭模型池</h3>
          <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>家长统一维护可用模型；子女可在其中选择并保存自己的偏好。</p>
        </div>
        <Button onClick={openCreate}><Plus className="mr-2 size-4" aria-hidden="true" />添加模型</Button>
      </header>

      {poolQuery.isLoading && <p className="py-8 text-sm" style={{ color: 'var(--color-text-secondary)' }}>正在加载家庭模型池…</p>}
      {poolQuery.isError && <div className="py-8"><p className="text-sm" style={{ color: 'var(--color-loss)' }}>无法加载家庭模型池。</p><Button className="mt-3" size="sm" variant="outline" onClick={() => void poolQuery.refetch()}>重试</Button></div>}
      {!poolQuery.isLoading && !poolQuery.isError && endpoints.length === 0 && <p className="py-8 text-sm" style={{ color: 'var(--color-text-secondary)' }}>暂未添加家庭模型。</p>}

      {!poolQuery.isLoading && !poolQuery.isError && endpoints.length > 0 && <div className="space-y-4">
        <label className="grid max-w-sm gap-1.5 text-sm font-medium" htmlFor="household-default-model" style={{ color: 'var(--color-text-primary)' }}>
          默认模型
          <Select
            id="household-default-model"
            aria-label="默认模型"
            value={defaultEndpointId ?? ''}
            disabled={setDefault.isPending}
            onChange={(event) => void updateDefault(event.target.value || null)}
          >
            <option value="">未设置默认模型</option>
            {enabledEndpoints.map((endpoint) => <option key={endpoint.endpoint_id} value={endpoint.endpoint_id}>{endpoint.display_name}</option>)}
          </Select>
        </label>
        {defaultEndpointId && <Button size="sm" variant="outline" disabled={setDefault.isPending} onClick={() => void updateDefault(null)}>清除默认模型</Button>}
        {actionError && <p role="alert" className="text-sm" style={{ color: 'var(--color-loss)' }}>{actionError}</p>}

        <div className="divide-y" style={{ borderColor: 'var(--color-border-muted)' }}>
          {endpoints.map((endpoint) => {
            const isDefault = endpoint.endpoint_id === defaultEndpointId;
            return <article key={endpoint.endpoint_id} className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>{endpoint.display_name}</h4>
                  {isDefault && <span className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium" style={{ backgroundColor: 'var(--color-accent-soft)', color: 'var(--color-accent-primary)' }}><Star className="size-3" aria-hidden="true" />默认模型</span>}
                  {!endpoint.enabled && <span className="rounded-md px-2 py-0.5 text-xs font-medium" style={{ backgroundColor: 'var(--color-bg-surface)', color: 'var(--color-text-tertiary)' }}>已停用</span>}
                </div>
                <p className="font-mono text-xs break-all" style={{ color: 'var(--color-text-secondary)' }}>{endpoint.provider} / {endpoint.model_id}</p>
                {endpoint.base_url && <p className="text-xs break-all" style={{ color: 'var(--color-text-tertiary)' }}>{endpoint.base_url}</p>}
                {endpoint.masked_api_key && <p className="flex items-center gap-1 text-xs" style={{ color: 'var(--color-text-tertiary)' }}><KeyRound className="size-3" aria-hidden="true" />{endpoint.masked_api_key}</p>}
              </div>
              <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                <label className="inline-flex h-10 items-center gap-2 rounded-md border px-3 text-sm" style={{ borderColor: 'var(--color-border-default)', color: 'var(--color-text-secondary)' }}>
                  <input
                    type="checkbox"
                    checked={endpoint.enabled}
                    disabled={updateEndpoint.isPending}
                    onChange={() => void updateEnabled(endpoint)}
                    aria-label={`${endpoint.enabled ? '禁用' : '启用'} ${endpoint.display_name}`}
                  />
                  <Power className="size-4" aria-hidden="true" />{endpoint.enabled ? '已启用' : '已停用'}
                </label>
                {!isDefault && endpoint.enabled && <Button size="sm" variant="outline" disabled={setDefault.isPending} onClick={() => void updateDefault(endpoint.endpoint_id)}><Check className="mr-2 size-4" aria-hidden="true" />设为默认</Button>}
                <TooltipProvider delayDuration={300}>
                  <Tooltip>
                    <TooltipTrigger asChild><Button size="icon" variant="outline" aria-label={`编辑 ${endpoint.display_name}`} onClick={() => openEdit(endpoint)}><Pencil className="size-4" aria-hidden="true" /></Button></TooltipTrigger>
                    <TooltipContent>编辑模型</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild><Button size="icon" variant="destructive" aria-label={`删除 ${endpoint.display_name}`} onClick={() => setDeleteTarget(endpoint)}><Trash2 className="size-4" aria-hidden="true" /></Button></TooltipTrigger>
                    <TooltipContent>删除模型</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </article>;
          })}
        </div>
      </div>}

      <Dialog open={dialogOpen} onOpenChange={closeDialog}>
        <DialogContent variant="centered" className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? '编辑家庭模型' : '添加家庭模型'}</DialogTitle>
            <DialogDescription>模型凭证仅由家庭管理员维护，子女无法查看或修改。</DialogDescription>
          </DialogHeader>
          <form className="grid gap-4" onSubmit={(event) => void submit(event)}>
            <label className="grid gap-1.5 text-sm font-medium" htmlFor="family-model-display-name">显示名称<Input id="family-model-display-name" value={form.displayName} onChange={(event) => setForm((current) => ({ ...current, displayName: event.target.value }))} required maxLength={128} /></label>
            <label className="grid gap-1.5 text-sm font-medium" htmlFor="family-model-provider">提供方<Input id="family-model-provider" value={form.provider} onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value }))} required maxLength={64} autoCapitalize="none" /></label>
            <label className="grid gap-1.5 text-sm font-medium" htmlFor="family-model-id">模型 ID<Input id="family-model-id" value={form.modelId} onChange={(event) => setForm((current) => ({ ...current, modelId: event.target.value }))} required maxLength={255} autoCapitalize="none" /></label>
            <label className="grid gap-1.5 text-sm font-medium" htmlFor="family-model-base-url">Base URL（可选）<Input id="family-model-base-url" type="url" value={form.baseUrl} onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))} maxLength={2048} placeholder="https://" /></label>
            <label className="grid gap-1.5 text-sm font-medium" htmlFor="family-model-api-key">API Key（可选）<Input id="family-model-api-key" type="password" value={form.apiKey} disabled={form.clearApiKey} onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))} autoComplete="new-password" maxLength={4096} /></label>
            {editing?.masked_api_key && <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}><input type="checkbox" checked={form.clearApiKey} onChange={(event) => setForm((current) => ({ ...current, clearApiKey: event.target.checked, apiKey: event.target.checked ? '' : current.apiKey }))} />清除当前 API Key</label>}
            <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}><input type="checkbox" checked={form.enabled} onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))} />启用此模型</label>
            {formError && <p role="alert" className="text-sm" style={{ color: 'var(--color-loss)' }}>{formError}</p>}
            <DialogFooter><Button type="submit" disabled={isSaving}>{isSaving ? '正在保存' : '保存模型'}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除家庭模型"
        message={`删除“${deleteTarget?.display_name ?? ''}”后，已选择它的子女将自动回退到可用的默认模型。`}
        confirmLabel="删除模型"
        onConfirm={confirmDelete}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
      />
    </section>
  );
}
