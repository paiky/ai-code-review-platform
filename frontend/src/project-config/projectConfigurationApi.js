import { fetchApi } from '../api.js';

function queryString(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.set(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}

export function fetchProjects(filters, pagination) {
  return fetchApi(`/api/projects${queryString({
    keyword: filters.keyword?.trim(),
    targetType: filters.targetType,
    notificationStatus: filters.notificationStatus,
    reviewStatus: filters.reviewStatus,
    pageNo: pagination.pageNo,
    pageSize: pagination.pageSize
  })}`);
}

export function fetchProjectConfiguration(projectId) {
  return fetchApi(`/api/projects/${projectId}/configuration`);
}

export function saveProjectConfiguration(projectId, payload) {
  return fetchApi(`/api/projects/${projectId}/configuration`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
}

export function fetchProjectConfigurationDefaults(targetType) {
  return fetchApi(`/api/projects/configuration-defaults${queryString({ targetType })}`);
}

export function fetchTargetDetectionPreview(projectId) {
  return fetchApi(`/api/projects/${projectId}/target-type-auto-detection/preview`);
}

export function applyTargetDetection(projectId, payload) {
  return fetchApi(`/api/projects/${projectId}/target-type-auto-detection`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
}

export function fetchNotificationWebhooks(filters = {}, pagination = { pageNo: 1, pageSize: 100 }) {
  return fetchApi(`/api/notification-webhooks${queryString({
    keyword: filters.keyword?.trim(),
    status: filters.status,
    lastTestStatus: filters.lastTestStatus,
    pageNo: pagination.pageNo,
    pageSize: pagination.pageSize
  })}`);
}

export function createNotificationWebhook(payload) {
  return fetchApi('/api/notification-webhooks', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function updateNotificationWebhook(webhookId, payload) {
  return fetchApi(`/api/notification-webhooks/${webhookId}`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
}

export function deleteNotificationWebhook(webhookId) {
  return fetchApi(`/api/notification-webhooks/${webhookId}`, { method: 'DELETE' });
}

export function testNotificationWebhook(webhookId) {
  return fetchApi(`/api/notification-webhooks/${webhookId}/test`, { method: 'POST' });
}

export function fetchNotificationWebhookProjects(webhookId) {
  return fetchApi(`/api/notification-webhooks/${webhookId}/projects`);
}

export function previewBatchNotificationWebhooks(payload) {
  return fetchApi('/api/projects/notification-webhooks/batch/preview', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function saveBatchNotificationWebhooks(payload) {
  return fetchApi('/api/projects/notification-webhooks/batch', {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
}

export function fetchTargetPathMappings() {
  return fetchApi('/api/target-type-path-mappings');
}

export function saveTargetPathMappings(items) {
  return fetchApi('/api/target-type-path-mappings', {
    method: 'PUT',
    body: JSON.stringify({ items })
  });
}

export function fetchReviewProfiles() {
  return fetchApi('/api/code-quality-review-profiles');
}
