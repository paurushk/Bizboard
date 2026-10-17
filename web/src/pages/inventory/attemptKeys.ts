import { isDefinitiveRejection, newIdempotencyKey } from '@/api/client';

/**
 * One Idempotency-Key per attempt at one action (INV-IDR-01).
 *
 * The key is kept while the outcome is unknown (lost response, timeout, 5xx), so a retry cannot
 * post twice. It is dropped when the action succeeded or the server refused it: the next click is
 * a new request, and reusing the old key would replay the refusal (or be rejected as a different
 * body after the user corrects the form).
 */
export class AttemptKeys {
  private readonly keys = new Map<string, string>();

  get(name: string): string {
    let key = this.keys.get(name);
    if (!key) {
      key = newIdempotencyKey();
      this.keys.set(name, key);
    }
    return key;
  }

  /** Call with no error after success, or with the error after a failure. */
  settle(name: string, error?: unknown): void {
    if (error === undefined || isDefinitiveRejection(error)) this.keys.delete(name);
  }
}
