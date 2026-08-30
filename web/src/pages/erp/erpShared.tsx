import type { ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Typography from '@mui/material/Typography';

import { isCrmEnabled, isManufacturingEnabled, isPayrollEnabled } from '@/config/features';
import { t } from '@/i18n';
import { PageShell } from '@/pages/phase/phaseShared';

export type ErpModule = 'manufacturing' | 'payroll' | 'crm';

const MVP_BANNERS: Record<ErpModule, string> = {
  manufacturing: 'preview.manufacturing',
  payroll: 'preview.payroll',
  crm: 'preview.crm',
};

const ENABLE_HINTS: Record<ErpModule, string> = {
  manufacturing: 'This module isn’t enabled for your company. Ask your account owner to enable it, or contact support.',
  payroll: 'This module isn’t enabled for your company. Ask your account owner to enable it, or contact support.',
  crm: 'This module isn’t enabled for your company. Ask your account owner to enable it, or contact support.',
};

export function isModuleEnabled(module: ErpModule): boolean {
  switch (module) {
    case 'manufacturing':
      return isManufacturingEnabled();
    case 'payroll':
      return isPayrollEnabled();
    case 'crm':
      return isCrmEnabled();
  }
}

export function MvpModuleBanner({ module }: { module: ErpModule }) {
  return (
    <Alert severity="info" sx={{ mb: 2 }}>
      <Typography variant="body2">{t(MVP_BANNERS[module])}</Typography>
    </Alert>
  );
}

export function ModuleGate({
  module,
  title,
  children,
}: {
  module: ErpModule;
  title: string;
  children: ReactNode;
}) {
  if (!isModuleEnabled(module)) {
    return (
      <PageShell title={title}>
        <Typography>{ENABLE_HINTS[module]}</Typography>
      </PageShell>
    );
  }
  return <>{children}</>;
}
