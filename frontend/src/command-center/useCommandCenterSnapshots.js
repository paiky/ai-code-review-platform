import { useCallback, useEffect, useRef, useState } from 'react';

import { createVisibilityRefreshLifecycle } from '../visibilityRefreshLifecycle.js';
import {
  normalizeRuntimeSnapshot,
  RUNTIME_STALE_MS,
  snapshotFreshness
} from './commandCenterModel.js';
import { loadRuntimeSnapshot } from './commandCenterApi.js';


const RUNTIME_INTERVAL_MS = 5_000;
const INITIAL_RESOURCE = {
  data: null,
  loading: true,
  error: '',
  updatedAt: null
};

export const COMMAND_CENTER_POLLING_DIAGNOSTICS_KEY = '__commandCenterPollingDiagnostics';


export function useCommandCenterRuntimeSnapshot() {
  const [runtimeState, setRuntimeState] = useState(INITIAL_RESOURCE);
  const requestRef = useRef(null);
  const timerRef = useRef(null);
  const sequenceRef = useRef(0);
  const lifecycleRef = useRef(null);
  const mountedRef = useRef(false);
  const diagnosticsRef = useRef(createPollingDiagnostics());

  const syncDiagnosticAttributes = useCallback(() => {
    const root = document.querySelector('.command-center-page');
    if (!root) return;
    const snapshot = readPollingDiagnostics({
      diagnostics: diagnosticsRef.current,
      timer: timerRef.current,
      lifecycle: lifecycleRef.current
    });
    const attributes = {
      'data-command-center-runtime-started': snapshot.runtime.started,
      'data-command-center-runtime-completed': snapshot.runtime.completed,
      'data-command-center-runtime-aborted': snapshot.runtime.aborted,
      'data-command-center-runtime-deduplicated': snapshot.runtime.deduplicated,
      'data-command-center-active-timers': snapshot.activeTimerCount,
      'data-command-center-polling-listeners': snapshot.lifecycle?.listenerRegistrationCount ?? 0,
      'data-command-center-suppressed-focus': snapshot.lifecycle?.suppressedFocusCount ?? 0
    };
    for (const [name, value] of Object.entries(attributes)) {
      root.setAttribute(name, String(value));
    }
  }, []);

  const clearTimer = useCallback(() => {
    if (timerRef.current === null) return;
    window.clearTimeout(timerRef.current);
    timerRef.current = null;
    syncDiagnosticAttributes();
  }, [syncDiagnosticAttributes]);

  const abortRequest = useCallback(() => {
    const request = requestRef.current;
    if (!request) return;
    requestRef.current = null;
    request.controller.abort();
    diagnosticsRef.current.aborted += 1;
    diagnosticsRef.current.active = 0;
    syncDiagnosticAttributes();
  }, [syncDiagnosticAttributes]);

  const loadRuntime = useCallback(() => {
    clearTimer();
    if (!mountedRef.current || isDocumentHidden()) return Promise.resolve(null);
    const existing = requestRef.current;
    if (existing) {
      diagnosticsRef.current.deduplicated += 1;
      syncDiagnosticAttributes();
      return existing.promise;
    }

    const controller = new AbortController();
    const sequence = sequenceRef.current + 1;
    const request = { controller, promise: null, sequence };
    sequenceRef.current = sequence;
    requestRef.current = request;
    diagnosticsRef.current.started += 1;
    diagnosticsRef.current.active = 1;
    syncDiagnosticAttributes();
    setRuntimeState(current => ({ ...current, loading: true, error: '' }));

    request.promise = (async () => {
      try {
        const raw = await loadRuntimeSnapshot({ signal: controller.signal });
        if (
          !mountedRef.current
          || controller.signal.aborted
          || sequence !== sequenceRef.current
        ) return null;
        const data = normalizeRuntimeSnapshot(raw);
        diagnosticsRef.current.completed += 1;
        syncDiagnosticAttributes();
        setRuntimeState({
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
          || sequence !== sequenceRef.current
        ) return null;
        diagnosticsRef.current.failed += 1;
        syncDiagnosticAttributes();
        setRuntimeState(current => ({
          ...current,
          data: current.data
            ? {
                ...current.data,
                freshness: snapshotFreshness(
                  current.data.generatedAt,
                  RUNTIME_STALE_MS
                )
              }
            : null,
          loading: false,
          error: error instanceof Error
            ? error.message
            : 'Runtime 数据加载失败'
        }));
        return null;
      } finally {
        if (requestRef.current === request) {
          requestRef.current = null;
          diagnosticsRef.current.active = 0;
          if (
            mountedRef.current
            && !isDocumentHidden()
            && sequence === sequenceRef.current
          ) {
            timerRef.current = window.setTimeout(loadRuntime, RUNTIME_INTERVAL_MS);
          }
          syncDiagnosticAttributes();
        }
      }
    })();
    return request.promise;
  }, [clearTimer, syncDiagnosticAttributes]);

  const reload = useCallback(() => loadRuntime(), [loadRuntime]);

  useEffect(() => {
    mountedRef.current = true;
    const pause = () => {
      clearTimer();
      abortRequest();
    };
    const lifecycle = createVisibilityRefreshLifecycle({
      onPause: pause,
      onResume: reload
    });
    lifecycleRef.current = lifecycle;
    const diagnosticsReader = () => readPollingDiagnostics({
      diagnostics: diagnosticsRef.current,
      timer: timerRef.current,
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
    runtimeLoading: runtimeState.loading,
    runtimeError: runtimeState.error,
    reload
  };
}


function createPollingDiagnostics() {
  return { started: 0, completed: 0, failed: 0, aborted: 0, deduplicated: 0, active: 0 };
}


function readPollingDiagnostics({ diagnostics, timer, lifecycle }) {
  return {
    runtime: { ...diagnostics },
    activeTimerCount: Number(timer !== null),
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
