import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { getCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { isSetupWizardEnabled } from '@/config/features';
import { findFirstNavPath } from '@/navigation/menu';
import { shouldForceSetup } from '@/onboarding/shouldForceSetup';
import { DashboardPage } from '@/pages/DashboardPage';
import { LimitedAccessLanding } from '@/pages/LimitedAccessLanding';
import { canViewFinancialReports } from '@/utils/permissions';

/** BB-000528 / UX-Fix: home route — dashboard for finance users, direct operational workspace for staff. */
export function HomePage() {
  const { user } = useAuth();
  const needsCompany = Boolean(isSetupWizardEnabled() && user?.role === 'OWNER');
  const companyQuery = useQuery({
    queryKey: ['company'],
    queryFn: getCompany,
    enabled: needsCompany,
  });

  if (needsCompany && companyQuery.isLoading) {
    return (
      <Box minHeight="40vh" display="grid" sx={{ placeItems: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (shouldForceSetup(user, companyQuery.data ?? user?.company)) {
    return <Navigate to="/setup" replace />;
  }
  if (canViewFinancialReports(user)) {
    return <DashboardPage />;
  }
  const firstPath = findFirstNavPath(user);
  if (firstPath) {
    return <Navigate to={firstPath} replace />;
  }
  return <LimitedAccessLanding />;
}
