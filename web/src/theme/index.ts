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
    MuiButtonBase: {
      styleOverrides: {
        root: ({ theme }) => ({
          '&:focus-visible': {
            outline: `2px solid ${theme.palette.primary.main}`,
            outlineOffset: 2,
          },
        }),
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
    },
    // UX-N07: table containers scroll sideways on phones; keep them keyboard-reachable.
    MuiTableContainer: { defaultProps: { tabIndex: 0 } },
    // A2-4: icon controls and checkboxes stay at least 44px on a phone.
    MuiIconButton: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.down('sm')]: { minWidth: 44, minHeight: 44 },
        }),
      },
    },
    MuiCheckbox: {
      styleOverrides: {
        root: ({ theme }) => ({
          [theme.breakpoints.down('sm')]: { padding: 10 },
        }),
      },
    },
    // UX-N05: MUI's disabled helper text (38% black) fails 4.5:1 contrast. Helper
    // text explains why a field is off, so keep it readable while disabled.
    MuiFormHelperText: {
      styleOverrides: {
        root: ({ theme }) => ({
          '&.Mui-disabled': { color: theme.palette.text.secondary },
        }),
      },
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
