import { fetchApi } from '../api.js';


export function loadRuntimeSnapshot({ signal } = {}) {
  return fetchApi('/api/command-center/runtime', { signal });
}


export function loadGovernanceSnapshot({ signal } = {}) {
  return fetchApi('/api/command-center/governance', { signal });
}
