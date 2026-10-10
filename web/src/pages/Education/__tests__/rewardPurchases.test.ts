import { beforeEach, describe, expect, it } from 'vitest';
import { runAuthResets } from '@/lib/authResets';
import { pendingPurchaseKey, readPendingPurchase, savePendingPurchase } from '../rewardPurchases';
import '../rewardPurchases';

beforeEach(() => localStorage.clear());
describe('persisted reward purchases', () => {
  it('retains an uncertain request under the same student and household', () => {
    const request = { pack_type: 'daily' as const, expected_price: 5, idempotency_key: 'f135a740-03bd-40c5-98f2-dba824f81871' };
    const key = pendingPurchaseKey('family', 'student'); savePendingPurchase(key, request);
    expect(readPendingPurchase(key)).toEqual(request);
    expect(readPendingPurchase(pendingPurchaseKey('other-family', 'student'))).toBeNull();
  });
  it('rejects corrupted values and invalid persisted prices', () => {
    const key = pendingPurchaseKey('family', 'student');
    localStorage.setItem(key, '{'); expect(readPendingPurchase(key)).toBeNull();
    localStorage.setItem(key, JSON.stringify({ pack_type: 'rare', expected_price: -1, idempotency_key: 'bad' }));
    expect(readPendingPurchase(key)).toBeNull(); expect(localStorage.getItem(key)).toBeNull();
  });
  it('clears only reward requests at logout', () => {
    const key = pendingPurchaseKey('family', 'student'); localStorage.setItem(key, '{}'); localStorage.setItem('theme', 'nasa');
    runAuthResets(); expect(localStorage.getItem(key)).toBeNull(); expect(localStorage.getItem('theme')).toBe('nasa');
  });
});
