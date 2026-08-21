import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router-dom';

/**
 * BB-000751: unknown routes previously fell through to a silent redirect to
 * "/", giving no indication a link was bad. This shows the URL that failed
 * and offers a way back, instead of quietly swapping in the dashboard.
 */
export function NotFoundPage() {
  return (
    <Box
      sx={{
        minHeight: '60vh',
        display: 'grid',
        placeItems: 'center',
        textAlign: 'center',
        px: 2,
      }}
    >
      <Stack spacing={2} alignItems="center">
        <Typography variant="h2" fontWeight={700} color="text.secondary">
          404
        </Typography>
        <Typography variant="h6">Page not found</Typography>
        <Typography color="text.secondary" sx={{ maxWidth: 420 }}>
          There's nothing at{' '}
          <Typography component="span" fontFamily="monospace">
            {typeof window !== 'undefined' ? window.location.pathname : ''}
          </Typography>
          . It may have moved, or the link might be out of date.
        </Typography>
        <Button component={RouterLink} to="/" variant="contained">
          Back to Dashboard
        </Button>
      </Stack>
    </Box>
  );
}
