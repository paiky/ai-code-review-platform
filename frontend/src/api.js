export async function fetchApi(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  });
  const body = await response.json();
  if (!response.ok || body.success === false) {
    throw new Error(body.message || `Request failed: ${response.status}`);
  }
  return body.data;
}

export function riskColor(level) {
  switch (level) {
    case 'CRITICAL':
      return 'red';
    case 'HIGH':
      return 'volcano';
    case 'MEDIUM':
      return 'gold';
    case 'LOW':
      return 'green';
    default:
      return 'default';
  }
}

export function statusColor(status) {
  switch (status) {
    case 'SUCCESS':
      return 'green';
    case 'FAILED':
      return 'red';
    case 'RUNNING':
      return 'processing';
    case 'PENDING':
      return 'blue';
    default:
      return 'default';
  }
}