export function educationErrorMessage(error: unknown, fallback: string): string {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } } | null
  )?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  return error instanceof Error && error.message ? error.message : fallback;
}
