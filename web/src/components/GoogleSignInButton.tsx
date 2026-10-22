import { useEffect, useRef } from 'react';
import Box from '@mui/material/Box';
import { googleClientId, loadGoogleIdentity } from '@/auth/googleIdentity';

/**
 * WP-ID5: Google's own "Sign in with Google" button (Google Identity Services). Renders nothing
 * unless VITE_GOOGLE_CLIENT_ID is set. ``onCredential`` gets the Google ID token, which the
 * server checks (audience, issuer, expiry, verified email) before signing in or signing up.
 */
export function GoogleSignInButton({
  onCredential,
  text = 'signin_with',
}: {
  onCredential: (credential: string) => void;
  text?: 'signin_with' | 'signup_with' | 'continue_with';
}) {
  const host = useRef<HTMLDivElement | null>(null);
  const callback = useRef(onCredential);
  useEffect(() => {
    callback.current = onCredential;
  }, [onCredential]);
  const clientId = googleClientId();

  useEffect(() => {
    if (!clientId) return undefined;
    let cancelled = false;
    void loadGoogleIdentity().then((google) => {
      if (cancelled || !google || !host.current) return;
      google.accounts.id.initialize({
        client_id: clientId,
        callback: (resp: { credential?: string }) => {
          if (resp.credential) callback.current(resp.credential);
        },
        ux_mode: 'popup',
      });
      google.accounts.id.renderButton(host.current, { type: 'standard', theme: 'outline', size: 'large', text });
    });
    return () => {
      cancelled = true;
    };
  }, [clientId, text]);

  if (!clientId) return null;
  return <Box ref={host} sx={{ minHeight: 44 }} data-testid="google-signin" />;
}
