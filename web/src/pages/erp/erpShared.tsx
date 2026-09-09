import type { ReactNode } from 'react';
import Typography from '@mui/material/Typography';

import { HonestyBanner } from '@/components/HonestyBanner';
import { isCrmEnabled, isManufacturingEnabled, isPayrollEnabled } from '@/config/features';
import { t } from '@/i18n';
import { PageShell } from '@/pages/phase/phaseShared';

export type ErpModule = 'manufacturing' | 'payroll' | 'crm';

const MVP_BANNERS: Record<ErpModule, string> = {
  manufacturing: 'honesty.manufacturingMvp',
  payroll: 'honesty.payrollNot24q',
  crm: 'honesty.crmNotebook',
};

const ENABLE_HINTS: Record<ErpModule, string> = {
  manufacturing: 'erp.moduleDisabled',
  payroll: 'erp.payrollDisabled',
  crm: 'erp.moduleDisabled',
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
  return <HonestyBanner messageKey={MVP_BANNERS[module]} />;
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
        <Typography>{t(ENABLE_HINTS[module])}</Typography>
      </PageShell>
    );
  }
  return <>{children}</>;
}
