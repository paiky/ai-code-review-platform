import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createVisibilityRefreshLifecycle } from '../visibilityRefreshLifecycle.js';
import {
  GOVERNANCE_STALE_MS,
  normalizeGovernanceSnapshot,
  normalizeRuntimeSnapshot,
  RUNTIME_STALE_MS
} from './commandCenterModel.js';
import { loadGovernanceSnapshot, loadRuntimeSnapshot } from './commandCenterApi.js';
import {
  createSnapshotResourceState,
  reduceSnapshotResourceState
} from './commandCenterResourceState.js';


export const RUNTIME_INTERVAL_MS = 5_000;
export const GOVERNANCE_INTERVAL_MS = 60_000;
export const COMMAND_CENTER_POLLING_DIAGNOSTICS_KEY = '__commandCenterPollingDiagnostics';

const RESOURCE_CONFIGS = Object.freeze({
  runtime: {
    intervalMs: RUNTIME_INTERVAL_MS,
    staleAfterMs: RUNTIME_STALE_MS,
    load: loadRuntimeSnapshot,
    normalize: normalizeRuntimeSnapshot,
    fallbackError: 'Runtime 数据加载失败'
  },
  governance: {
    intervalMs: GOVERNANCE_INTERVAL_MS,
    staleAfterMs: GOVERNANCE_STALE_MS,
    load: loadGovernanceSnapshot,
    normalize: normalizeGovernanceSnapshot,
    fallbackError: '质量统计加载失败'
  }
});
const RESOURCE_KEYS = Object.freeze(Object.keys(RESOURCE_CONFIGS));


export function useCommandCenterSnapshots() {
  const [resources, setResources] = useState(createInitialResources);
  const requestRef = useRef(createKeyedValue(null));
  const timerRef = useRef(createKeyedValue(null));
  const sequenceRef = useRef(createKeyedValue(0));
  const lifecycleRef = useRef(null);
  const mountedRef = useRef(false);
  const diagnosticsRef = useRef(createPollingDiagnostics());

  const syncDiagnosticAttributes = useCallback(() => {
    const root = document.querySelector('.command-center-page');
    if (!root) return;
    const snapshot = readPollingDiagnostics({
      diagnostics: diagnosticsRef.current,
      timers: timerRef.current,
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

  const clearResourceTimer = useCallback((resourceKey) => {
    const timer = timerRef.current[resourceKey];
    if (timer === null) return;
    window.clearTimeout(timer);
    timerRef.current[resourceKey] = null;
    syncDiagnosticAttributes();
  }, [syncDiagnosticAttributes]);

  const abortResourceRequest = useCallback((resourceKey) => {
    const request = requestRef.current[resourceKey];
    if (!request) return;
    requestRef.current[resourceKey] = null;
    request.controller.abort();
    diagnosticsRef.current[resourceKey].aborted += 1;
    diagnosticsRef.current[resourceKey].active = 0;
    syncDiagnosticAttributes();
  }, [syncDiagnosticAttributes]);

  const loadResource = useCallback((resourceKey) => {
    const config = RESOURCE_CONFIGS[resourceKey];
    if (!config) return Promise.resolve(null);
    clearResourceTimer(resourceKey);
    if (!mountedRef.current || isDocumentHidden()) return Promise.resolve(null);

    const existing = requestRef.current[resourceKey];
    if (existing) {
      diagnosticsRef.current[resourceKey].deduplicated += 1;
      syncDiagnosticAttributes();
      return existing.promise;
    }

    const controller = new AbortController();
    const sequence = sequenceRef.current[resourceKey] + 1;
    const request = { controller, promise: null, sequence };
    sequenceRef.current[resourceKey] = sequence;
    requestRef.current[resourceKey] = request;
    diagnosticsRef.current[resourceKey].started += 1;
    diagnosticsRef.current[resourceKey].active = 1;
    syncDiagnosticAttributes();
    updateResource(setResources, resourceKey, { type: 'LOAD_STARTED' });

    request.promise = (async () => {
      try {
        const raw = await config.load({ signal: controller.signal });
        if (
          !mountedRef.current
          || controller.signal.aborted
          || sequence !== sequenceRef.current[resourceKey]
        ) return null;
        const data = config.normalize(raw);
        diagnosticsRef.current[resourceKey].completed += 1;
        syncDiagnosticAttributes();
        updateResource(setResources, resourceKey, {
          type: 'LOAD_SUCCEEDED',
          data,
          updatedAt: new Date().toISOString()
        });
        return data;
      } catch (error) {
        if (
          controller.signal.aborted
          || !mountedRef.current
          || sequence !== sequenceRef.current[resourceKey]
        ) return null;
        diagnosticsRef.current[resourceKey].failed += 1;
        syncDiagnosticAttributes();
        updateResource(setResources, resourceKey, {
          type: 'LOAD_FAILED',
          error,
          staleAfterMs: config.staleAfterMs,
          fallbackError: config.fallbackError
        });
        return null;
      } finally {
        if (requestRef.current[resourceKey] === request) {
          requestRef.current[resourceKey] = null;
          diagnosticsRef.current[resourceKey].active = 0;
          if (
            mountedRef.current
            && !isDocumentHidden()
            && sequence === sequenceRef.current[resourceKey]
          ) {
            timerRef.current[resourceKey] = window.setTimeout(
              () => loadResource(resourceKey),
              config.intervalMs
            );
          }
          syncDiagnosticAttributes();
        }
      }
    })();
    return request.promise;
  }, [clearResourceTimer, syncDiagnosticAttributes]);

  const reload = useCallback(
    () => Promise.all(RESOURCE_KEYS.map(resourceKey => loadResource(resourceKey))),
    [loadResource]
  );
  const reloadRuntime = useCallback(() => loadResource('runtime'), [loadResource]);
  const reloadGovernance = useCallback(() => loadResource('governance'), [loadResource]);

  useEffect(() => {
    mountedRef.current = true;
    const pause = () => {
      for (const resourceKey of RESOURCE_KEYS) {
        clearResourceTimer(resourceKey);
        abortResourceRequest(resourceKey);
      }
    };
    const lifecycle = createVisibilityRefreshLifecycle({
      onPause: pause,
      onResume: reload
    });
    lifecycleRef.current = lifecycle;
    const diagnosticsReader = () => readPollingDiagnostics({
      diagnostics: diagnosticsRef.current,
      timers: timerRef.current,
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
  }, [abortResourceRequest, clearResourceTimer, reload, syncDiagnosticAttributes]);

  return useMemo(() => ({
    runtime: resources.runtime.data,
    runtimeLoading: resources.runtime.loading,
    runtimeError: resources.runtime.error,
    governance: resources.governance.data,
    governanceLoading: resources.governance.loading,
    governanceError: resources.governance.error,
    reload,
    reloadRuntime,
    reloadGovernance
  }), [reload, reloadGovernance, reloadRuntime, resources]);
}


function createInitialResources() {
  return Object.fromEntries(
    RESOURCE_KEYS.map(resourceKey => [resourceKey, createSnapshotResourceState()])
  );
}


function createKeyedValue(value) {
  return Object.fromEntries(RESOURCE_KEYS.map(resourceKey => [resourceKey, value]));
}


function updateResource(setResources, resourceKey, event) {
  setResources(current => ({
    ...current,
    [resourceKey]: reduceSnapshotResourceState(current[resourceKey], event)
  }));
}


function createResourceDiagnostics() {
  return { started: 0, completed: 0, failed: 0, aborted: 0, deduplicated: 0, active: 0 };
}


function createPollingDiagnostics() {
  return Object.fromEntries(
    RESOURCE_KEYS.map(resourceKey => [resourceKey, createResourceDiagnostics()])
  );
}


function readPollingDiagnostics({ diagnostics, timers, lifecycle }) {
  return {
    runtime: { ...diagnostics.runtime },
    governance: { ...diagnostics.governance },
    activeTimerCount: RESOURCE_KEYS.filter(resourceKey => timers[resourceKey] !== null).length,
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
