const IDLE_LANE = Object.freeze({ activity: 'idle', queued: false, running: false });


export function commandCenterMotionScene(presentation, runtimeLoading = false) {
  const fresh = !runtimeLoading && presentation?.resources?.runtime?.state === 'FRESH';
  if (!fresh) return pausedScene();

  const agent = laneActivity(presentation?.agentLane);
  const standard = laneActivity(presentation?.standardLane);
  const activity = agent.running || standard.running
    ? 'running'
    : agent.queued || standard.queued
      ? 'queued'
      : 'idle';
  const fallbackActivity = realFallbackActivity(presentation?.standardLane);

  return {
    activity,
    fallbackActive: fallbackActivity !== 'idle',
    lanes: { agent, standard },
    connections: {
      'queue-engine': connectionActivity(activity),
      'engine-agent': connectionActivity(agent.activity),
      'engine-standard': connectionActivity(standard.activity),
      'agent-result': connectionActivity(agent.running ? 'running' : 'idle'),
      'standard-result': connectionActivity(standard.running ? 'running' : 'idle'),
      'agent-standard': connectionActivity(fallbackActivity)
    }
  };
}


export function commandCenterMotionState(presentation, runtimeLoading = false) {
  return commandCenterMotionScene(presentation, runtimeLoading).activity;
}


function pausedScene() {
  return {
    activity: 'paused',
    fallbackActive: false,
    lanes: { agent: IDLE_LANE, standard: IDLE_LANE },
    connections: {
      'queue-engine': connectionActivity('idle'),
      'engine-agent': connectionActivity('idle'),
      'engine-standard': connectionActivity('idle'),
      'agent-result': connectionActivity('idle'),
      'standard-result': connectionActivity('idle'),
      'agent-standard': connectionActivity('idle')
    }
  };
}


function laneActivity(lane) {
  const running = positive(lane?.running);
  const queued = positive(lane?.queued);
  return {
    activity: running ? 'running' : queued ? 'queued' : 'idle',
    queued,
    running
  };
}


function realFallbackActivity(standardLane) {
  if (
    positive(standardLane?.running)
    && (standardLane?.runningItems || []).some(item => item?.fallback === true)
  ) return 'running';
  return positive(standardLane?.queued) && standardLane?.nextQueued?.fallback === true
    ? 'queued'
    : 'idle';
}


function connectionActivity(activity) {
  return {
    activity,
    active: activity === 'queued' || activity === 'running'
  };
}


function positive(value) {
  return Number.isFinite(Number(value)) && Number(value) > 0;
}
