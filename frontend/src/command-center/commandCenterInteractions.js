export function restoreCommandCenterFocus(trigger, fallback) {
  const target = trigger?.isConnected ? trigger : fallback;
  if (!target?.isConnected || typeof target.focus !== 'function') return false;
  target.focus();
  return true;
}
