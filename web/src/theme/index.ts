import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#0F766E',
      dark: '#0B5A54',
      light: '#14B8A6',
      contrastText: '#FFFFFF',
    },
    secondary: {
      main: '#B45309',
      contrastText: '#FFFFFF',
    },
    background: {
      default: '#F3F6F5',
      paper: '#FFFFFF',
    },
    success: { main: '#15803D' },
    warning: { main: '#C2410C' },
    error: { main: '#B91C1C' },
    info: { main: '#0369A1' },
    divider: '#D5E0DC',
  },
  typography: {
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif',
    h1: { fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif', fontWeight: 700 },
    h2: { fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif', fontWeight: 700 },
    h3: { fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif', fontWeight: 700 },
    h4: { fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif', fontWeight: 650 },
    h5: { fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif', fontWeight: 650 },
    h6: { fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif', fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundImage: 'linear-gradient(120deg, #0F766E 0%, #0B5A54 55%, #134E4A 100%)',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          borderRight: '1px solid #D5E0DC',
          background:
            'linear-gradient(180deg, #FFFFFF 0%, #F7FBFA 100%)',
        },
      },
    },
  },
});
