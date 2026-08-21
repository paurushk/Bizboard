import Alert from '@mui/material/Alert';

export function DisclaimerBanner({
  children,
  severity = 'info',
}: {
  children: React.ReactNode;
  severity?: 'info' | 'warning' | 'error' | 'success';
}) {
  return (
    <Alert severity={severity} variant="outlined" sx={{ '& .MuiAlert-message': { width: '100%' } }}>
      {children}
    </Alert>
  );
}
