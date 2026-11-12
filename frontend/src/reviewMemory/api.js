function root(projectId) {
  return `/api/projects/${encodeURIComponent(projectId)}/review-memory`;
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => null);
  if (!response.ok || !body?.success) {
    const error = new Error(body?.message || `请求失败（HTTP ${response.status}）`);
    error.status = response.status;
    error.code = body?.code;
    throw error;
  }
  return body.data;
}

export function listSources(projectId, filters, signal) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value != null) query.set(key, String(value));
  });
  return request(`${root(projectId)}/sources?${query}`, { signal });
}

export function getSource(projectId, sourceId, signal) {
  return request(`${root(projectId)}/sources/${sourceId}`, { signal });
}

export function getSourceImpact(projectId, sourceId) {
  return request(`${root(projectId)}/sources/${sourceId}/impact`);
}

export function getBinding(projectId, sourceId, signal) {
  return request(`${root(projectId)}/sources/${sourceId}/binding`, { signal });
}

export function listSharedSources(filters, signal) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value != null) query.set(key, String(value));
  });
  return request(`/api/review-memory/shared-sources?${query}`, { signal });
}

export function getSharedSource(sourceId, signal) {
  return request(`/api/review-memory/shared-sources/${sourceId}`, { signal });
}

export function mutateSource(projectId, suffix, method, payload) {
  return request(`${root(projectId)}/${suffix}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(payload == null ? {} : { body: JSON.stringify(payload) })
  });
}

export function uploadSource(projectId, file, metadata, signal) {
  const form = new FormData();
  form.append('file', file);
  form.append('metadata', JSON.stringify(metadata));
  return request(`${root(projectId)}/uploads`, {
    method: 'POST',
    body: form,
    signal
  });
}

export async function downloadOriginal(projectId, source) {
  const path =
    projectId == null
      ? `/api/review-memory/shared-sources/${source.id}/original`
      : `${root(projectId)}/sources/${source.id}/original`;
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.message || '原件下载失败');
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = source.originalFilename || 'original';
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
