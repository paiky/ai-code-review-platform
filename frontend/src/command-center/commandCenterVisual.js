export function commandCenterMotionState(presentation, runtimeLoading) {
  return !runtimeLoading && presentation?.hud?.resourceState === 'FRESH'
    ? 'enabled'
    : 'paused';
}
