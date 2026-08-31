import { useEffect, useState } from 'react';
import Button from '@mui/material/Button';
import ButtonGroup from '@mui/material/ButtonGroup';
import { getLocale, setLocale, subscribeLocale, t } from '@/i18n';

export function LocaleSwitcher() {
  const [locale, setLocaleState] = useState(getLocale());

  useEffect(() => subscribeLocale(() => setLocaleState(getLocale())), []);

  const switchTo = (next: 'en' | 'hi' | 'ta' | 'gu') => {
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

  return (
    <ButtonGroup size="small" variant="outlined" aria-label="Language">
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
      <Button
        variant={locale === 'ta' ? 'contained' : 'outlined'}
        onClick={() => switchTo('ta')}
        sx={locale === 'ta' ? undefined : inactiveSx}
      >
        {t('locale.switchToTamil')}
      </Button>
      <Button
        variant={locale === 'gu' ? 'contained' : 'outlined'}
        onClick={() => switchTo('gu')}
        sx={locale === 'gu' ? undefined : inactiveSx}
      >
        {t('locale.switchToGujarati')}
      </Button>
    </ButtonGroup>
  );
}
