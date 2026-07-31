import { useCallback, useEffect, useRef, useState } from 'react';

import {
  loadGovernanceSnapshot,
  loadRuntimeSnapshot
} from './commandCenterApi.js';


const INITIAL_STATE = {
  runtime: null,
  governance: null,
  loading: true,
  error: ''
};


export function useCommandCenterSnapshots() {
  const [state, setState] = useState(INITIAL_STATE);
  const activeRequestRef = useRef(null);
  const requestSequenceRef = useRef(0);

  const reload = useCallback(async () => {
    activeRequestRef.current?.abort();
    const controller = new AbortController();
    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;
    activeRequestRef.current = controller;
    setState(current => ({ ...current, loading: true, error: '' }));

    try {
      const [runtime, governance] = await Promise.all([
        loadRuntimeSnapshot({ signal: controller.signal }),
        loadGovernanceSnapshot({ signal: controller.signal })
      ]);
      if (requestSequence !== requestSequenceRef.current) return;
      setState({
        runtime,
        governance,
        loading: false,
        error: ''
      });
    } catch (error) {
      if (controller.signal.aborted || requestSequence !== requestSequenceRef.current) return;
      setState(current => ({
        ...current,
        loading: false,
        error: error instanceof Error ? error.message : 'Command Center 数据加载失败'
      }));
    }
  }, []);

  useEffect(() => {
    reload();
    return () => {
      activeRequestRef.current?.abort();
    };
  }, [reload]);

  return {
    ...state,
    reload
  };
}
