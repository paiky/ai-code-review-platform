import { createTheme } from '@mui/material/styles';

export const appMuiTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#2563eb',
      contrastText: '#ffffff'
    },
    secondary: {
      main: '#ec4899'
    },
    background: {
      default: '#f5f7f8',
      paper: '#ffffff'
    },
    text: {
      primary: '#1f2933',
      secondary: '#5f6b76'
    }
  },
  shape: {
    borderRadius: 8
  },
  typography: {
    fontFamily: 'Inter, "Segoe UI", Arial, "Microsoft YaHei", sans-serif',
    h1: { letterSpacing: 0 },
    h2: { letterSpacing: 0 },
    h3: { letterSpacing: 0 },
    h4: { letterSpacing: 0 },
    h5: { letterSpacing: 0 },
    h6: { letterSpacing: 0 },
    button: {
      letterSpacing: 0,
      textTransform: 'none'
    }
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: 'var(--mui-palette-background-default)'
        },
        '#root': {
          minHeight: '100vh'
        }
      }
    },
    MuiButton: {
      defaultProps: {
        disableElevation: true
      },
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontWeight: 600
        }
      }
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 8
        }
      }
    }
  }
});
