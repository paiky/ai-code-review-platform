import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { appMuiTheme } from './muiTheme.js';

export function MuiAppShell({ children }) {
  return (
    <ThemeProvider theme={appMuiTheme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  );
}
