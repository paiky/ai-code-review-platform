export const COMMAND_CENTER_CONNECTIONS = Object.freeze([
  Object.freeze({ id: 'queue-engine', from: 'queue-out', to: 'engine-in', token: 'intake', kind: 'direct' }),
  Object.freeze({ id: 'engine-agent', from: 'engine-agent-out', to: 'agent-in', token: 'agent', kind: 'branch' }),
  Object.freeze({ id: 'engine-standard', from: 'engine-standard-out', to: 'standard-in', token: 'standard', kind: 'branch' }),
  Object.freeze({ id: 'agent-result', from: 'agent-out', to: 'result-agent-in', token: 'agent', kind: 'result' }),
  Object.freeze({ id: 'standard-result', from: 'standard-out', to: 'result-standard-in', token: 'standard', kind: 'result' }),
  Object.freeze({ id: 'agent-standard', from: 'agent-down', to: 'standard-up', token: 'fallback', kind: 'fallback' })
]);


export function measureCommandCenterTopology(container) {
  const containerRect = safeRect(container);
  if (!containerRect || containerRect.width <= 0 || containerRect.height <= 0) {
    return emptyTopology();
  }

  const paths = [];
  for (const connection of COMMAND_CENTER_CONNECTIONS) {
    const from = measurePort(container, containerRect, connection.from);
    const to = measurePort(container, containerRect, connection.to);
    if (!from || !to) return emptyTopology(containerRect);
    paths.push({
      ...connection,
      from,
      to,
      d: connectionPath(connection.kind, from, to)
    });
  }
  return {
    ready: true,
    width: roundCoordinate(containerRect.width),
    height: roundCoordinate(containerRect.height),
    paths
  };
}


export function observeCommandCenterTopology(
  container,
  onSnapshot,
  { ResizeObserverClass = globalThis.ResizeObserver } = {}
) {
  let lastSignature = '';
  let disconnected = false;
  const publish = () => {
    if (disconnected) return false;
    const snapshot = measureCommandCenterTopology(container);
    const signature = topologySignature(snapshot);
    if (signature === lastSignature) return false;
    lastSignature = signature;
    onSnapshot(snapshot);
    return true;
  };

  publish();
  const observer = typeof ResizeObserverClass === 'function'
    ? new ResizeObserverClass(publish)
    : null;
  if (observer) {
    observer.observe(container);
    container.querySelectorAll('[data-command-center-map-node="true"]')
      .forEach(node => observer.observe(node));
  }

  return {
    measure: publish,
    disconnect() {
      if (disconnected) return;
      disconnected = true;
      observer?.disconnect();
    }
  };
}


function measurePort(container, containerRect, portId) {
  const element = container.querySelector(`[data-command-center-port="${portId}"]`);
  const rect = safeRect(element);
  if (!rect || rect.width <= 0 || rect.height <= 0) return null;
  return {
    x: roundCoordinate(rect.left + rect.width / 2 - containerRect.left),
    y: roundCoordinate(rect.top + rect.height / 2 - containerRect.top)
  };
}


function connectionPath(kind, from, to) {
  if (kind === 'fallback') return verticalBridge(from, to);
  if (kind === 'direct') {
    return Math.abs(to.y - from.y) < 1
      ? horizontalStraight(from, to)
      : roundedHorizontalCable(from, to, 0.5);
  }
  return roundedHorizontalCable(from, to, kind === 'result' ? 0.66 : 0.42);
}


function horizontalStraight(from, to) {
  const startX = roundCoordinate(from.x + 14);
  const endX = roundCoordinate(to.x - 10);
  return [
    `M ${from.x} ${from.y}`,
    `L ${startX} ${from.y}`,
    `H ${endX}`
  ].join(' ');
}


function roundedHorizontalCable(from, to, bendRatio) {
  const startX = roundCoordinate(from.x + 14);
  const endX = roundCoordinate(to.x - 10);
  const span = endX - startX;
  const deltaY = to.y - from.y;
  if (Math.abs(deltaY) < 1) return horizontalStraight(from, to);
  if (Math.abs(span) < 1) {
    return [
      `M ${from.x} ${from.y}`,
      `L ${startX} ${from.y}`,
      `L ${endX} ${to.y}`
    ].join(' ');
  }

  const directionY = deltaY > 0 ? 1 : -1;
  const radius = roundCoordinate(Math.min(14, Math.abs(deltaY) / 2, Math.abs(span) / 5));
  const minimumBend = Math.min(startX, endX) + radius;
  const maximumBend = Math.max(startX, endX) - radius;
  const proposedBend = roundCoordinate(startX + span * bendRatio);
  const bendX = roundCoordinate(clamp(proposedBend, minimumBend, maximumBend));
  const firstCornerX = roundCoordinate(bendX - Math.sign(span) * radius);
  const secondCornerX = roundCoordinate(bendX + Math.sign(span) * radius);
  const firstCornerY = roundCoordinate(from.y + directionY * radius);
  const secondCornerY = roundCoordinate(to.y - directionY * radius);

  return [
    `M ${from.x} ${from.y}`,
    `L ${startX} ${from.y}`,
    `H ${firstCornerX}`,
    `Q ${bendX} ${from.y} ${bendX} ${firstCornerY}`,
    `V ${secondCornerY}`,
    `Q ${bendX} ${to.y} ${secondCornerX} ${to.y}`,
    `H ${endX}`
  ].join(' ');
}


function verticalBridge(from, to) {
  const startY = roundCoordinate(from.y + 14);
  const endY = roundCoordinate(to.y - 10);
  const deltaX = to.x - from.x;
  const span = endY - startY;
  if (Math.abs(deltaX) < 1 || Math.abs(span) < 28) {
    return [
      `M ${from.x} ${from.y}`,
      `L ${from.x} ${startY}`,
      `V ${endY}`
    ].join(' ');
  }

  const directionX = deltaX > 0 ? 1 : -1;
  const directionY = span > 0 ? 1 : -1;
  const radius = roundCoordinate(Math.min(12, Math.abs(deltaX) / 2, Math.abs(span) / 5));
  const bendY = roundCoordinate(startY + span / 2);
  return [
    `M ${from.x} ${from.y}`,
    `L ${from.x} ${startY}`,
    `V ${roundCoordinate(bendY - directionY * radius)}`,
    `Q ${from.x} ${bendY} ${roundCoordinate(from.x + directionX * radius)} ${bendY}`,
    `H ${roundCoordinate(to.x - directionX * radius)}`,
    `Q ${to.x} ${bendY} ${to.x} ${roundCoordinate(bendY + directionY * radius)}`,
    `V ${endY}`
  ].join(' ');
}


function safeRect(element) {
  if (!element || typeof element.getBoundingClientRect !== 'function') return null;
  try {
    return element.getBoundingClientRect();
  } catch {
    return null;
  }
}


function emptyTopology(rect = null) {
  return {
    ready: false,
    width: roundCoordinate(rect?.width || 0),
    height: roundCoordinate(rect?.height || 0),
    paths: []
  };
}


function topologySignature(snapshot) {
  return JSON.stringify([
    snapshot.ready,
    snapshot.width,
    snapshot.height,
    snapshot.paths.map(path => [path.id, path.d])
  ]);
}


function roundCoordinate(value) {
  return Math.round(Number(value) * 10) / 10;
}


function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}
