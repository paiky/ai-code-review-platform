export const COMMAND_CENTER_PREVIEW_PHASES = Object.freeze([
  Object.freeze({ id: 'AGENT_QUEUED', durationMs: 800, label: 'Agent 排队' }),
  Object.freeze({ id: 'AGENT_RUNNING', durationMs: 2400, label: 'Agent 审查' }),
  Object.freeze({ id: 'FALLBACK_HANDOFF', durationMs: 1200, label: '降级交接' }),
  Object.freeze({ id: 'STANDARD_FALLBACK', durationMs: 1400, label: 'Standard 兜底' }),
  Object.freeze({ id: 'RESETTING', durationMs: 200, label: '恢复实时状态' })
]);

const IDLE_LANE = Object.freeze({ activity: 'idle', queued: false, running: false });


export function canStartCommandCenterPreview({
  runtimeState,
  runtimeLoading = false,
  firstLoadComplete = false,
  realActivity = 'paused'
} = {}) {
  return runtimeState === 'FRESH'
    && runtimeLoading === false
    && firstLoadComplete === true
    && realActivity === 'idle';
}


export function commandCenterPreviewScene(phaseId) {
  switch (phaseId) {
    case 'AGENT_QUEUED':
      return scene({
        activity: 'queued',
        agent: lane('queued'),
        connections: {
          'queue-engine': 'queued',
          'engine-agent': 'queued'
        }
      });
    case 'AGENT_RUNNING':
      return scene({
        activity: 'running',
        agent: lane('running'),
        connections: {
          'queue-engine': 'running',
          'engine-agent': 'running',
          'agent-result': 'running'
        }
      });
    case 'FALLBACK_HANDOFF':
      return scene({
        activity: 'running',
        fallbackActive: true,
        connections: {
          'queue-engine': 'running',
          'engine-agent': 'running',
          'agent-standard': 'running'
        }
      });
    case 'STANDARD_FALLBACK':
      return scene({
        activity: 'running',
        fallbackActive: true,
        standard: lane('running'),
        connections: {
          'queue-engine': 'running',
          'engine-agent': 'running',
          'agent-standard': 'running',
          'standard-result': 'running'
        }
      });
    case 'RESETTING':
      return scene({ activity: 'idle' });
    default:
      return null;
  }
}


export function composeCommandCenterPreviewScene(realScene, phaseId) {
  if (!phaseId || realScene?.activity !== 'idle') return realScene;
  return commandCenterPreviewScene(phaseId) || realScene;
}


export function commandCenterPreviewPhaseLabel(phaseId) {
  return COMMAND_CENTER_PREVIEW_PHASES.find(phase => phase.id === phaseId)?.label || '';
}


export function createCommandCenterPreviewController({
  onPhaseChange,
  setTimeoutFn = globalThis.setTimeout,
  clearTimeoutFn = globalThis.clearTimeout
} = {}) {
  let active = false;
  let disposed = false;
  let phaseIndex = -1;
  let timer = null;

  const publish = phase => {
    if (typeof onPhaseChange === 'function') onPhaseChange(phase);
  };
  const clearTimer = () => {
    if (timer === null) return;
    clearTimeoutFn(timer);
    timer = null;
  };
  const finish = (notify = true) => {
    clearTimer();
    const wasActive = active;
    active = false;
    phaseIndex = -1;
    if (notify && wasActive) publish(null);
    return wasActive;
  };
  const enterPhase = index => {
    if (!active || disposed) return;
    clearTimer();
    phaseIndex = index;
    const phase = COMMAND_CENTER_PREVIEW_PHASES[index];
    if (!phase) {
      finish();
      return;
    }
    publish(phase.id);
    timer = setTimeoutFn(() => {
      timer = null;
      enterPhase(index + 1);
    }, phase.durationMs);
  };

  return {
    start(availability) {
      if (disposed || active || !canStartCommandCenterPreview(availability)) return false;
      active = true;
      enterPhase(0);
      return true;
    },
    syncAvailability(availability) {
      if (!active || canStartCommandCenterPreview(availability)) return false;
      return finish();
    },
    cancel() {
      return finish();
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      finish(false);
    },
    getState() {
      return {
        active,
        disposed,
        phase: phaseIndex >= 0 ? COMMAND_CENTER_PREVIEW_PHASES[phaseIndex].id : null,
        pendingTimerCount: timer === null ? 0 : 1
      };
    }
  };
}


function scene({
  activity,
  fallbackActive = false,
  agent = IDLE_LANE,
  standard = IDLE_LANE,
  connections = {}
}) {
  return {
    activity,
    fallbackActive,
    lanes: { agent, standard },
    connections: Object.fromEntries([
      'queue-engine',
      'engine-agent',
      'engine-standard',
      'agent-result',
      'standard-result',
      'agent-standard'
    ].map(id => [id, connection(connections[id] || 'idle')]))
  };
}


function lane(activity) {
  return {
    activity,
    queued: activity === 'queued',
    running: activity === 'running'
  };
}


function connection(activity) {
  return {
    activity,
    active: activity === 'queued' || activity === 'running'
  };
}
