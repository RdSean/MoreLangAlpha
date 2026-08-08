/**
 * Idempotency key for a logical send (v4 attempt chain).
 *
 * One UUID per logical send, REUSED when the same send is retransmitted after
 * a failure whose response never arrived: the server dedups on `request_key`
 * (HTTP 409 `duplicate_request`), so a lost-response resubmit adopts the
 * already-accepted run instead of opening a duplicate turn. The key is
 * consumed (cleared) as soon as response headers arrive — from then on an
 * identical message is a genuinely new logical send.
 */

export interface RequestKeyTracker {
  /** Key for this send; reuses the pending key iff the fingerprint matches (a retransmit). */
  take: (fingerprint: string) => string;
  /** The send reached the server (headers arrived) — the pending key is consumed. */
  clear: () => void;
}

function createRequestKey(): string {
  const webCrypto = globalThis.crypto;
  if (typeof webCrypto?.randomUUID === 'function') return webCrypto.randomUUID();

  const bytes = new Uint8Array(16);
  if (typeof webCrypto?.getRandomValues === 'function') {
    webCrypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function createRequestKeyTracker(): RequestKeyTracker {
  let pending: { key: string; fingerprint: string } | null = null;

  function take(fingerprint: string): string {
    if (pending && pending.fingerprint === fingerprint) {
      return pending.key;
    }
    pending = { key: createRequestKey(), fingerprint };
    return pending.key;
  }

  function clear(): void {
    pending = null;
  }

  return { take, clear };
}
