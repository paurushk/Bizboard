import { useEffect, useState } from 'react';
import Button from '@mui/material/Button';
import ButtonGroup from '@mui/material/ButtonGroup';
import { useTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import { getLocale, setLocale, subscribeLocale, t } from '@/i18n';

export function LocaleSwitcher({ compact }: { compact?: boolean } = {}) {
  const [locale, setLocaleState] = useState(getLocale());
  // On a phone the two-button group pushed हिंदी off the right edge of the header
  // (found by the axe phone run). There, one button offers the other language.
  const narrow = useMediaQuery(useTheme().breakpoints.down('sm'));
  const single = compact ?? narrow;

  useEffect(() => subscribeLocale(() => setLocaleState(getLocale())), []);

  useEffect(() => {
    // R-084: stale ta/gu localStorage from older builds → fall back to en.
    // setLocale notifies subscribers, so the state follows through the subscription above.
    if (getLocale() === 'ta' || getLocale() === 'gu') setLocale('en');
  }, []);

  const switchTo = (next: 'en' | 'hi') => {
    if (next === getLocale()) return;
    setLocale(next);
    setLocaleState(next);
  };

  // BB-000751: this sits on the teal AppBar. MUI's default "outlined" variant
  // colors text/border from theme.palette.primary.main, which is the same
  // teal as the AppBar background — the inactive button's label was
  // rendering invisible (1:1 contrast). Force white text/border for the
  // inactive state so it's readable regardless of the surrounding surface.
  const inactiveSx = {
    color: 'common.white',
    borderColor: 'rgba(255, 255, 255, 0.6)',
    '&:hover': { borderColor: 'common.white', bgcolor: 'rgba(255, 255, 255, 0.08)' },
  } as const;

  if (single) {
    const other = locale === 'hi' ? 'en' : 'hi';
    return (
      <Button
        size="small"
        variant="outlined"
        lang={other}
        aria-label={`${t('locale.language')}: ${other === 'hi' ? t('locale.switchToHindi') : t('locale.switchToEnglish')}`}
        onClick={() => switchTo(other)}
        sx={{ ...inactiveSx, minWidth: 0, flexShrink: 0 }}
      >
        {other === 'hi' ? t('locale.switchToHindi') : t('locale.switchToEnglish')}
      </Button>
    );
  }

  return (
    <ButtonGroup size="small" variant="outlined" aria-label={t('locale.language')}>
      <Button
        variant={locale === 'en' ? 'contained' : 'outlined'}
        onClick={() => switchTo('en')}
        sx={locale === 'en' ? undefined : inactiveSx}
      >
        {t('locale.switchToEnglish')}
      </Button>
      <Button
        variant={locale === 'hi' ? 'contained' : 'outlined'}
        onClick={() => switchTo('hi')}
        sx={locale === 'hi' ? undefined : inactiveSx}
      >
        {t('locale.switchToHindi')}
      </Button>
    </ButtonGroup>
  );
}
