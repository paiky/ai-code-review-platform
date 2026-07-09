import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import 'antd/dist/reset.css';
import './styles.css';
import App from './App.jsx';
import { MuiAppShell } from './MuiAppShell.jsx';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <MuiAppShell>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </MuiAppShell>
  </React.StrictMode>
);
