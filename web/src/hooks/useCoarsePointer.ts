import useMediaQuery from '@mui/material/useMediaQuery';

/**
 * True on a touch-first device (phone, tablet). There, focusing a field on page load opens the
 * keyboard and scrolls past the fields above it, and keyboard-shortcut hints do not apply
 * (BB-100 F5). False wherever matchMedia is missing, so desktop behaviour is the default.
 */
export function useCoarsePointer(): boolean {
  return useMediaQuery('(pointer: coarse)', { noSsr: true });
}
