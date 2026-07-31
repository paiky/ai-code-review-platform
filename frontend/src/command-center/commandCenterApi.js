import { fetchApi } from '../api.js';


export function loadRuntimeSnapshot({ signal, windowHours = 24, activeLimit = 50, alertLimit = 20 } = {}) {
  const params = new URLSearchParams({
    windowHours: String(windowHours),
    activeLimit: String(activeLimit),
    alertLimit: String(alertLimit)
  });
  return fetchApi(`/api/command-center/runtime?${params.toString()}`, { signal });
}


export function loadGovernanceSnapshot({ signal, windowHours = 24 } = {}) {
  const params = new URLSearchParams({ windowHours: String(windowHours) });
  return fetchApi(`/api/command-center/governance?${params.toString()}`, { signal });
}
