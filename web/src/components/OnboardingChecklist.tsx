import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { alpha } from '@mui/material/styles';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import StorefrontIcon from '@mui/icons-material/Storefront';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import Inventory2Icon from '@mui/icons-material/Inventory2';
import ReceiptIcon from '@mui/icons-material/Receipt';
import { Link as RouterLink } from 'react-router-dom';
import { t } from '@/i18n';
import type { Company } from '@/types/domain';
import { isPosEnabled } from '@/config/features';
import { trackOnboardingEvent } from '@/onboarding/analytics';
import {
  companyStepIncompleteNeedsGst,
  firstBillHelpTextKey,
  shopDetailsComplete,
} from '@/onboarding/taxHints';

interface Props {
  company?: Company | null;
  productCount?: number;
  invoiceCount?: number;
}

export function OnboardingChecklist({ company, productCount = 0, invoiceCount = 0 }: Props) {
  const needsGst = companyStepIncompleteNeedsGst(company);
  const hasCompanyDetails = shopDetailsComplete(company) && !needsGst;
  const hasBankDetails = Boolean(company?.bankAccount || company?.upiId);
  const hasProducts = productCount > 0;
  const hasInvoices = invoiceCount > 0;

  const completedSteps = [hasCompanyDetails, hasBankDetails, hasProducts, hasInvoices].filter(
    Boolean,
  ).length;
  const progressPercent = (completedSteps / 4) * 100;

  if (company?.onboarding?.activationDone || (hasInvoices && completedSteps === 4)) {
    return null; // All done!
  }

  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 2, sm: 3 },
        borderRadius: 2,
        // F3-057: theme-token gradient/shadow so the card stays legible in dark mode.
        background: (theme) =>
          `linear-gradient(135deg, ${alpha(theme.palette.success.light, 0.18)} 0%, ${
            theme.palette.background.paper
          } 60%, ${alpha(theme.palette.primary.light, 0.1)} 100%)`,
        borderColor: 'primary.light',
        boxShadow: (theme) => `0 2px 8px ${alpha(theme.palette.primary.main, 0.12)}`,
      }}
    >
      <Stack spacing={2.5}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" gap={1}>
          <Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="h6" fontWeight={700} color="primary.dark">
                {t('onboarding.title')}
              </Typography>
              {/* F3-074: completedSteps === 4 (+ hasInvoices) always short-circuits
                  to the early `return null` above, so a 'success' branch here was
                  dead code — 3/4 is the highest state this chip can ever show. */}
              <Chip
                label={`${completedSteps} / 4 ${t('status.completed')}`}
                size="small"
                color={completedSteps === 3 ? 'success' : 'primary'}
                variant="outlined"
              />
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {t('onboarding.subtitle')}
            </Typography>
          </Box>
        </Stack>

        <Box sx={{ width: '100%' }}>
          <LinearProgress
            variant="determinate"
            value={progressPercent}
            sx={{ height: 6, borderRadius: 3 }}
          />
        </Box>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' },
            gap: 2,
          }}
        >
          {/* Step 1 */}
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              borderRadius: 1.5,
              bgcolor: hasCompanyDetails ? 'background.paper' : 'action.hover',
              borderLeft: '4px solid',
              borderLeftColor: hasCompanyDetails ? 'success.main' : 'primary.main',
            }}
          >
            <Stack direction="row" spacing={1.5} alignItems="flex-start">
              {hasCompanyDetails ? (
                <CheckCircleIcon color="success" sx={{ mt: 0.25 }} />
              ) : (
                <StorefrontIcon color="primary" sx={{ mt: 0.25 }} />
              )}
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  {t('onboarding.stepCompany')}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  {t(needsGst ? 'onboarding.stepCompanyDescGst' : 'onboarding.stepCompanyDesc')}
                </Typography>
                <Button
                  component={RouterLink}
                  to={needsGst ? '/settings/gst' : '/settings/company'}
                  size="small"
                  variant={hasCompanyDetails ? 'outlined' : 'contained'}
                  onClick={() =>
                    trackOnboardingEvent('onboarding_checklist_cta', {
                      step: 'company',
                      target: needsGst ? '/settings/gst' : '/settings/company',
                    })
                  }
                >
                  {t('onboarding.stepCompanyBtn')}
                </Button>
              </Box>
            </Stack>
          </Paper>

          {/* Step 2 */}
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              borderRadius: 1.5,
              bgcolor: hasBankDetails ? 'background.paper' : 'action.hover',
              borderLeft: '4px solid',
              borderLeftColor: hasBankDetails ? 'success.main' : 'primary.main',
            }}
          >
            <Stack direction="row" spacing={1.5} alignItems="flex-start">
              {hasBankDetails ? (
                <CheckCircleIcon color="success" sx={{ mt: 0.25 }} />
              ) : (
                <AccountBalanceIcon color="primary" sx={{ mt: 0.25 }} />
              )}
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  {t('onboarding.stepBank')}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  {t('onboarding.stepBankDesc')}
                </Typography>
                <Button
                  component={RouterLink}
                  to="/settings/company"
                  size="small"
                  variant={hasBankDetails ? 'outlined' : 'contained'}
                  onClick={() => trackOnboardingEvent('onboarding_checklist_cta', { step: 'payments' })}
                >
                  {t('onboarding.stepBankBtn')}
                </Button>
              </Box>
            </Stack>
          </Paper>

          {/* Step 3 */}
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              borderRadius: 1.5,
              bgcolor: hasProducts ? 'background.paper' : 'action.hover',
              borderLeft: '4px solid',
              borderLeftColor: hasProducts ? 'success.main' : 'primary.main',
            }}
          >
            <Stack direction="row" spacing={1.5} alignItems="flex-start">
              {hasProducts ? (
                <CheckCircleIcon color="success" sx={{ mt: 0.25 }} />
              ) : (
                <Inventory2Icon color="primary" sx={{ mt: 0.25 }} />
              )}
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  {t('onboarding.stepProduct')}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  {t('onboarding.stepProductDesc')}
                </Typography>
                <Button
                  component={RouterLink}
                  to="/inventory/products"
                  size="small"
                  variant={hasProducts ? 'outlined' : 'contained'}
                  onClick={() => trackOnboardingEvent('onboarding_checklist_cta', { step: 'catalog' })}
                >
                  {t('onboarding.stepProductBtn')}
                </Button>
              </Box>
            </Stack>
          </Paper>

          {/* Step 4 */}
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              borderRadius: 1.5,
              bgcolor: hasInvoices ? 'background.paper' : 'action.hover',
              borderLeft: '4px solid',
              borderLeftColor: hasInvoices ? 'success.main' : 'primary.main',
            }}
          >
            <Stack direction="row" spacing={1.5} alignItems="flex-start">
              {hasInvoices ? (
                <CheckCircleIcon color="success" sx={{ mt: 0.25 }} />
              ) : (
                <ReceiptIcon color="primary" sx={{ mt: 0.25 }} />
              )}
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  {t('onboarding.stepInvoice')}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  {t(firstBillHelpTextKey(company?.registrationType))}
                </Typography>
                <Stack direction="row" spacing={1}>
                  <Button
                    component={RouterLink}
                    to="/sales/new"
                    size="small"
                    variant={hasInvoices ? 'outlined' : 'contained'}
                    onClick={() => trackOnboardingEvent('onboarding_checklist_cta', { step: 'first_bill' })}
                  >
                    {t('onboarding.stepInvoiceBtn')}
                  </Button>
                  {isPosEnabled() ? (
                    <Button
                      component={RouterLink}
                      to="/pos"
                      size="small"
                      variant="outlined"
                      onClick={() => trackOnboardingEvent('onboarding_checklist_cta', { step: 'pos' })}
                    >
                      {t('nav.pos')}
                    </Button>
                  ) : null}
                </Stack>
              </Box>
            </Stack>
          </Paper>
        </Box>
      </Stack>
    </Paper>
  );
}
