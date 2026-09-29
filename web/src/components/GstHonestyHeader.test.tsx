import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { GstHonestyHeader } from '@/components/GstHonestyHeader';
import { t } from '@/i18n';

describe('GstHonestyHeader', () => {
  it('shows the worksheet sentence and a link to the GST portal', () => {
    render(<GstHonestyHeader />);
    expect(screen.getByText(t('gstHonesty.offlineAid'))).toBeTruthy();
    const link = screen.getByRole('link', { name: t('gstHonesty.filePortalLink') });
    expect(link.getAttribute('href')).toBe('https://www.gst.gov.in/');
    expect(screen.getByText(t('gstHonesty.offlineAid')).textContent ?? '').toMatch(/not filed/i);
  });
});
