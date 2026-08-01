export const FOCUS_AFTER_VISIBILITY_SUPPRESSION_MS = 500;


export function createVisibilityRefreshLifecycle({
  documentTarget = typeof document === 'undefined' ? null : document,
  windowTarget = typeof window === 'undefined' ? null : window,
  now = () => Date.now(),
  onPause = () => {},
  onResume = () => {},
  focusSuppressionMs = FOCUS_AFTER_VISIBILITY_SUPPRESSION_MS
} = {}) {
  let active = false;
  let paused = isHidden(documentTarget);
  let lastVisibilityResumeAt = Number.NEGATIVE_INFINITY;
  let listenerRegistrationCount = 0;
  let resumeCount = 0;
  let pauseCount = 0;
  let suppressedFocusCount = 0;

  const resume = source => {
    if (!active || isHidden(documentTarget)) return false;
    const timestamp = finiteNow(now);
    if (
      source === 'focus'
      && timestamp - lastVisibilityResumeAt <= focusSuppressionMs
    ) {
      suppressedFocusCount += 1;
      return false;
    }
    resumeCount += 1;
    onResume(source);
    return true;
  };

  const handleVisibility = () => {
    if (isHidden(documentTarget)) {
      if (!paused) {
        paused = true;
        pauseCount += 1;
        onPause('visibility');
      }
      return;
    }
    if (!paused) return;
    paused = false;
    lastVisibilityResumeAt = finiteNow(now);
    resume('visibility');
  };

  const handleFocus = () => {
    if (paused || isHidden(documentTarget)) return;
    resume('focus');
  };

  return {
    start() {
      if (active) return;
      active = true;
      paused = isHidden(documentTarget);
      documentTarget?.addEventListener?.('visibilitychange', handleVisibility);
      windowTarget?.addEventListener?.('focus', handleFocus);
      listenerRegistrationCount = Number(Boolean(documentTarget?.addEventListener))
        + Number(Boolean(windowTarget?.addEventListener));
      if (!paused) resume('mount');
    },
    dispose() {
      if (!active) return;
      active = false;
      documentTarget?.removeEventListener?.('visibilitychange', handleVisibility);
      windowTarget?.removeEventListener?.('focus', handleFocus);
      listenerRegistrationCount = 0;
    },
    getSnapshot() {
      return {
        active,
        paused,
        listenerRegistrationCount,
        resumeCount,
        pauseCount,
        suppressedFocusCount
      };
    }
  };
}


function isHidden(documentTarget) {
  return (
    documentTarget?.hidden === true
    || documentTarget?.visibilityState === 'hidden'
  );
}


function finiteNow(now) {
  const value = Number(now?.());
  return Number.isFinite(value) ? value : Date.now();
}
