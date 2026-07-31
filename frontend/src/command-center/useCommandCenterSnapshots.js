import { useCallback, useEffect, useRef, useState } from 'react';

import {
  GOVERNANCE_STALE_MS,
  normalizeGovernanceSnapshot,
  normalizeRuntimeSnapshot,
  RUNTIME_STALE_MS,
  snapshotFreshness
} from './commandCenterModel.js';
import {
  loadGovernanceSnapshot,
  loadRuntimeSnapshot
} from './commandCenterApi.js';


const RUNTIME_INTERVAL_MS = 5_000;
const GOVERNANCE_INTERVAL_MS = 60_000;
const INITIAL_RESOURCE = {
  data: null,
  loading: true,
  error: '',
  updatedAt: null
};


export function useCommandCenterSnapshots() {
  const [runtimeState, setRuntimeState] = useState(INITIAL_RESOURCE);
  const [governanceState, setGovernanceState] = useState(INITIAL_RESOURCE);
  const controllersRef = useRef({ runtime: null, governance: null });
  const timersRef = useRef({ runtime: null, governance: null });
  const sequencesRef = useRef({ runtime: 0, governance: 0 });
  const mountedRef = useRef(false);

  const clearTimer = useCallback(kind => {
    if (timersRef.current[kind]) {
      window.clearTimeout(timersRef.current[kind]);
      timersRef.current[kind] = null;
    }
  }, []);

  const abortRequest = useCallback(kind => {
    controllersRef.current[kind]?.abort();
    controllersRef.current[kind] = null;
  }, []);

  const loadResource = useCallback(async kind => {
    clearTimer(kind);
    abortRequest(kind);
    if (document.visibilityState === 'hidden') return;

    const controller = new AbortController();
    const sequence = sequencesRef.current[kind] + 1;
    sequencesRef.current[kind] = sequence;
    controllersRef.current[kind] = controller;
    const setResource = kind === 'runtime' ? setRuntimeState : setGovernanceState;
    setResource(current => ({ ...current, loading: true, error: '' }));

    try {
      const raw = kind === 'runtime'
        ? await loadRuntimeSnapshot({ signal: controller.signal })
        : await loadGovernanceSnapshot({ signal: controller.signal });
      if (!mountedRef.current || sequence !== sequencesRef.current[kind]) return;
      const data = kind === 'runtime'
        ? normalizeRuntimeSnapshot(raw)
        : normalizeGovernanceSnapshot(raw);
      setResource({
        data,
        loading: false,
        error: '',
        updatedAt: new Date().toISOString()
      });
    } catch (error) {
      if (
        controller.signal.aborted
        || !mountedRef.current
        || sequence !== sequencesRef.current[kind]
      ) return;
      setResource(current => ({
        ...current,
        data: current.data
          ? {
              ...current.data,
              freshness: snapshotFreshness(
                current.data.generatedAt,
                kind === 'runtime' ? RUNTIME_STALE_MS : GOVERNANCE_STALE_MS
              )
            }
          : null,
        loading: false,
        error: error instanceof Error
          ? error.message
          : `${kind === 'runtime' ? 'Runtime' : 'Governance'} 数据加载失败`
      }));
    } finally {
      if (controllersRef.current[kind] === controller) {
        controllersRef.current[kind] = null;
      }
      if (
        mountedRef.current
        && document.visibilityState !== 'hidden'
        && sequence === sequencesRef.current[kind]
      ) {
        timersRef.current[kind] = window.setTimeout(
          () => loadResource(kind),
          kind === 'runtime' ? RUNTIME_INTERVAL_MS : GOVERNANCE_INTERVAL_MS
        );
      }
    }
  }, [abortRequest, clearTimer]);

  const reload = useCallback(() => {
    loadResource('runtime');
    loadResource('governance');
  }, [loadResource]);

  useEffect(() => {
    mountedRef.current = true;
    const pause = () => {
      clearTimer('runtime');
      clearTimer('governance');
      abortRequest('runtime');
      abortRequest('governance');
    };
    const resume = () => {
      if (document.visibilityState !== 'hidden') reload();
    };
    const handleVisibility = () => {
      if (document.visibilityState === 'hidden') pause();
      else resume();
    };

    reload();
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('focus', resume);
    return () => {
      mountedRef.current = false;
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('focus', resume);
      pause();
    };
  }, [abortRequest, clearTimer, reload]);

  return {
    runtime: runtimeState.data,
    governance: governanceState.data,
    runtimeLoading: runtimeState.loading,
    governanceLoading: governanceState.loading,
    runtimeError: runtimeState.error,
    governanceError: governanceState.error,
    reload
  };
}
