import { registerAuthReset } from '@/lib/authResets';

export const REWARD_PURCHASE_STORAGE_PREFIX = 'education-reward-purchase:';
export function pendingPurchaseKey(householdId: string, studentId: string) {
  return `${REWARD_PURCHASE_STORAGE_PREFIX}${encodeURIComponent(householdId)}/${encodeURIComponent(studentId)}`;
}

// Auth loads this lightweight reset even when a restored session never opens rewards.
registerAuthReset(() => {
  try {
    const keys = Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index));
    for (const key of keys) if (key?.startsWith(REWARD_PURCHASE_STORAGE_PREFIX)) localStorage.removeItem(key);
  } catch { /* Storage may be disabled. */ }
});
