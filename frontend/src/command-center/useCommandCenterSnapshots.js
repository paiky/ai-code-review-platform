import { useCallback, useEffect, useRef, useState } from 'react';

import { createVisibilityRefreshLifecycle } from '../visibilityRefreshLifecycle.js';
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

export const COMMAND_CENTER_POLLING_DIAGNOSTICS_KEY = '__commandCenterPollingDiagnostics';


export function useCommandCenterSnapshots() {
  const [runtimeState, setRuntimeState] = useState(INITIAL_RESOURCE);
  const [governanceState, setGovernanceState] = useState(INITIAL_RESOURCE);
  const requestsRef = useRef({ runtime: null, governance: null });
  const timersRef = useRef({ runtime: null, governance: null });
  const sequencesRef = useRef({ runtime: 0, governance: 0 });
  const lifecycleRef = useRef(null);
  const mountedRef = useRef(false);
  const diagnosticsRef = useRef(createPollingDiagnostics());

  const syncDiagnosticAttributes = useCallback(() => {
    const root = document.querySelector('.command-center-page');
    if (!root) return;
    const snapshot = readPollingDiagnostics({
      diagnostics: diagnosticsRef.current,
      timers: timersRef.current,
      lifecycle: lifecycleRef.current
    });
    const attributes = {
      'data-command-center-runtime-started': snapshot.runtime.started,
      'data-command-center-runtime-completed': snapshot.runtime.completed,
      'data-command-center-runtime-aborted': snapshot.runtime.aborted,
      'data-command-center-runtime-deduplicated': snapshot.runtime.deduplicated,
      'data-command-center-governance-started': snapshot.governance.started,
      'data-command-center-governance-completed': snapshot.governance.completed,
      'data-command-center-governance-aborted': snapshot.governance.aborted,
      'data-command-center-governance-deduplicated': snapshot.governance.deduplicated,
      'data-command-center-active-timers': snapshot.activeTimerCount,
      'data-command-center-polling-listeners': snapshot.lifecycle?.listenerRegistrationCount ?? 0,
      'data-command-center-suppressed-focus': snapshot.lifecycle?.suppressedFocusCount ?? 0
    };
    for (const [name, value] of Object.entries(attributes)) {
      root.setAttribute(name, String(value));
    }
  }, []);

  const clearTimer = useCallback(kind => {
    if (timersRef.current[kind] !== null) {
      window.clearTimeout(timersRef.current[kind]);
      timersRef.current[kind] = null;
      syncDiagnosticAttributes();
    }
  }, [syncDiagnosticAttributes]);

  const abortRequest = useCallback(kind => {
    const request = requestsRef.current[kind];
    if (!request) return;
    requestsRef.current[kind] = null;
    request.controller.abort();
    diagnosticsRef.current[kind].aborted += 1;
    diagnosticsRef.current[kind].active = 0;
    syncDiagnosticAttributes();
  }, [syncDiagnosticAttributes]);

  const loadResource = useCallback(kind => {
    clearTimer(kind);
    if (!mountedRef.current || isDocumentHidden()) return Promise.resolve(null);
    const existing = requestsRef.current[kind];
    if (existing) {
      diagnosticsRef.current[kind].deduplicated += 1;
      syncDiagnosticAttributes();
      return existing.promise;
    }

    const controller = new AbortController();
    const sequence = sequencesRef.current[kind] + 1;
    const request = { controller, promise: null, sequence };
    const setResource = kind === 'runtime' ? setRuntimeState : setGovernanceState;
    sequencesRef.current[kind] = sequence;
    requestsRef.current[kind] = request;
    diagnosticsRef.current[kind].started += 1;
    diagnosticsRef.current[kind].active = 1;
    syncDiagnosticAttributes();
    setResource(current => ({ ...current, loading: true, error: '' }));

    request.promise = (async () => {
      try {
        const raw = kind === 'runtime'
          ? await loadRuntimeSnapshot({ signal: controller.signal })
          : await loadGovernanceSnapshot({ signal: controller.signal });
        if (
          !mountedRef.current
          || controller.signal.aborted
          || sequence !== sequencesRef.current[kind]
        ) return null;
        const data = kind === 'runtime'
          ? normalizeRuntimeSnapshot(raw)
          : normalizeGovernanceSnapshot(raw);
        diagnosticsRef.current[kind].completed += 1;
        syncDiagnosticAttributes();
        setResource({
          data,
          loading: false,
          error: '',
          updatedAt: new Date().toISOString()
        });
        return data;
      } catch (error) {
        if (
          controller.signal.aborted
          || !mountedRef.current
          || sequence !== sequencesRef.current[kind]
        ) return null;
        diagnosticsRef.current[kind].failed += 1;
        syncDiagnosticAttributes();
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
        return null;
      } finally {
        if (requestsRef.current[kind] === request) {
          requestsRef.current[kind] = null;
          diagnosticsRef.current[kind].active = 0;
          if (
            mountedRef.current
            && !isDocumentHidden()
            && sequence === sequencesRef.current[kind]
          ) {
            timersRef.current[kind] = window.setTimeout(
              () => loadResource(kind),
              kind === 'runtime' ? RUNTIME_INTERVAL_MS : GOVERNANCE_INTERVAL_MS
            );
          }
          syncDiagnosticAttributes();
        }
      }
    })();
    return request.promise;
  }, [clearTimer, syncDiagnosticAttributes]);

  const reload = useCallback(() => Promise.all([
    loadResource('runtime'),
    loadResource('governance')
  ]), [loadResource]);

  useEffect(() => {
    mountedRef.current = true;
    const pause = () => {
      clearTimer('runtime');
      clearTimer('governance');
      abortRequest('runtime');
      abortRequest('governance');
    };
    const lifecycle = createVisibilityRefreshLifecycle({
      onPause: pause,
      onResume: reload
    });
    lifecycleRef.current = lifecycle;
    const diagnosticsReader = () => readPollingDiagnostics({
      diagnostics: diagnosticsRef.current,
      timers: timersRef.current,
      lifecycle: lifecycleRef.current
    });
    attachPollingDiagnostics(diagnosticsReader);
    lifecycle.start();
    syncDiagnosticAttributes();

    return () => {
      mountedRef.current = false;
      lifecycle.dispose();
      lifecycleRef.current = null;
      pause();
      detachPollingDiagnostics(diagnosticsReader);
    };
  }, [abortRequest, clearTimer, reload, syncDiagnosticAttributes]);

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


function createPollingDiagnostics() {
  return {
    runtime: { started: 0, completed: 0, failed: 0, aborted: 0, deduplicated: 0, active: 0 },
    governance: { started: 0, completed: 0, failed: 0, aborted: 0, deduplicated: 0, active: 0 }
  };
}


function readPollingDiagnostics({ diagnostics, timers, lifecycle }) {
  return {
    runtime: { ...diagnostics.runtime },
    governance: { ...diagnostics.governance },
    activeTimerCount: Number(timers.runtime !== null) + Number(timers.governance !== null),
    lifecycle: lifecycle?.getSnapshot?.() || null
  };
}


function isDocumentHidden() {
  return document.hidden === true || document.visibilityState === 'hidden';
}


function attachPollingDiagnostics(reader) {
  try {
    window[COMMAND_CENTER_POLLING_DIAGNOSTICS_KEY] = reader;
  } catch {
    // Diagnostics must never affect Command Center polling.
  }
}


function detachPollingDiagnostics(reader) {
  if (window[COMMAND_CENTER_POLLING_DIAGNOSTICS_KEY] !== reader) return;
  try {
    delete window[COMMAND_CENTER_POLLING_DIAGNOSTICS_KEY];
  } catch {
    window[COMMAND_CENTER_POLLING_DIAGNOSTICS_KEY] = undefined;
  }
}
