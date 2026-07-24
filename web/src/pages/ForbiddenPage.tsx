import { Button, Paper, Stack, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

export function ForbiddenPage() {
  return (
    <Stack alignItems="center" justifyContent="center" sx={{ minHeight: '60vh', p: 3 }}>
      <Paper sx={{ p: 4, maxWidth: 480, textAlign: 'center' }}>
        <Typography variant="h5" gutterBottom>
          Access denied
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          You do not have permission to view this page. Ask your company owner to update your role
          permissions if you need access.
        </Typography>
        <Button component={RouterLink} to="/" variant="contained">
          Back to dashboard
        </Button>
      </Paper>
    </Stack>
  );
}
