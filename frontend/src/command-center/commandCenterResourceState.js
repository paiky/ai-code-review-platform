import { snapshotFreshness } from './commandCenterModel.js';


export function createSnapshotResourceState() {
  return {
    data: null,
    loading: true,
    error: '',
    updatedAt: null
  };
}


export function reduceSnapshotResourceState(current, event) {
  const state = current || createSnapshotResourceState();
  switch (event?.type) {
    case 'LOAD_STARTED':
      return {
        ...state,
        loading: true
      };
    case 'LOAD_SUCCEEDED':
      return {
        data: event.data || null,
        loading: false,
        error: '',
        updatedAt: event.updatedAt || new Date().toISOString()
      };
    case 'LOAD_FAILED':
      return {
        ...state,
        data: refreshRetainedSnapshot(
          state.data,
          event.staleAfterMs,
          event.now
        ),
        loading: false,
        error: errorMessage(event.error, event.fallbackError)
      };
    default:
      return state;
  }
}


export function presentSnapshotResource({ data, loading = false, error = '' } = {}) {
  const freshness = data?.freshness || 'EMPTY';
  const available = Boolean(data) && freshness !== 'EMPTY';
  const normalizedError = errorMessage(error);
  return {
    state: normalizedError
      ? available ? 'ERROR_RETAINED' : 'ERROR_EMPTY'
      : freshness,
    freshness,
    available,
    retained: Boolean(normalizedError && available),
    loading: Boolean(loading),
    generatedAt: available ? data.generatedAt || null : null,
    error: normalizedError || null,
    schemaCompatible: available ? data.schemaCompatible !== false : null,
    truncated: available ? Boolean(data.coverage?.truncated) : false
  };
}


function refreshRetainedSnapshot(data, staleAfterMs, now) {
  if (!data) return null;
  return {
    ...data,
    freshness: snapshotFreshness(
      data.generatedAt,
      staleAfterMs,
      Number.isFinite(now) ? now : Date.now()
    )
  };
}


function errorMessage(value, fallback = '') {
  if (value instanceof Error && value.message.trim()) return value.message.trim();
  if (typeof value === 'string' && value.trim()) return value.trim();
  return typeof fallback === 'string' ? fallback.trim() : '';
}
