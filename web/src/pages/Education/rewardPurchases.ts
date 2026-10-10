import { z } from 'zod';
export { pendingPurchaseKey } from './rewardPurchaseStorage';
import type { PurchaseRequest } from './rewardsApi';

const schema = z.object({
  pack_type: z.enum(['daily', 'featured', 'rare']),
  expected_price: z.number().int().min(1).max(10000), idempotency_key: z.string().uuid(),
});
export function readPendingPurchase(key: string): PurchaseRequest | null {
  try {
    const value = localStorage.getItem(key);
    if (!value) return null;
    const result = schema.safeParse(JSON.parse(value));
    if (result.success) return result.data;
    localStorage.removeItem(key);
  } catch { /* Unavailable storage or corrupted persisted data. */ }
  return null;
}
export function savePendingPurchase(key: string, request: PurchaseRequest) {
  // Persist before sending; never replace the key after an uncertain response.
  localStorage.setItem(key, JSON.stringify(request));
}
export function clearPendingPurchase(key: string) { localStorage.removeItem(key); }
