import { useCallback, useMemo, useRef, useState } from 'react';
import { Modal } from 'antd';
import { useNavigate } from 'react-router-dom';

import CommandCenterCanvas from './CommandCenterCanvas.jsx';
import { restoreCommandCenterFocus } from './commandCenterInteractions.js';
import { buildCommandCenterPresentation } from './commandCenterPresentation.js';
import {
  affectedRiskVisual,
  findingSeverityVisual,
  providerQualityVisual
} from './commandCenterQualityVisual.js';
import { commandCenterMotionScene } from './commandCenterVisual.js';
import { useCommandCenterSnapshots } from './useCommandCenterSnapshots.js';
import './commandCenter.css';


export default function CommandCenterPage() {
  const navigate = useNavigate();
  const [overflowZoneKey, setOverflowZoneKey] = useState(null);
  const overflowTriggerRef = useRef(null);
  const pageRef = useRef(null);
  const {
    runtime,
    runtimeLoading,
    runtimeError,
    governance,
    governanceLoading,
    governanceError,
    reload,
    reloadRuntime,
    reloadGovernance
  } = useCommandCenterSnapshots();
  const presentation = useMemo(
    () => buildCommandCenterPresentation({
      runtime,
      runtimeLoading,
      runtimeError,
      governance,
      governanceLoading,
      governanceError
    }),
    [
      governance,
      governanceError,
      governanceLoading,
      runtime,
      runtimeError,
      runtimeLoading
    ]
  );
  const motionScene = commandCenterMotionScene(presentation, runtimeLoading);
  const overflowLane = [presentation.agentLane, presentation.standardLane]
    .find(lane => lane.zoneKey === overflowZoneKey) || null;
  const navigateTo = useCallback(target => {
    if (typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')) {
      navigate(target);
    }
  }, [navigate]);
  const openOverflow = useCallback((lane, trigger) => {
    overflowTriggerRef.current = trigger || null;
    setOverflowZoneKey(lane.zoneKey);
  }, []);
  const closeOverflow = useCallback(() => setOverflowZoneKey(null), []);
  const restoreOverflowFocus = useCallback(() => {
    const trigger = overflowTriggerRef.current;
    overflowTriggerRef.current = null;
    restoreCommandCenterFocus(trigger, pageRef.current);
  }, []);

  return (
    <main
      ref={pageRef}
      className="command-center-page"
      tabIndex={-1}
      data-command-center-phase="LIVE_TOPOLOGY_M3"
      data-command-center-resource-state={presentation.resources.runtime.state}
      data-command-center-governance-state={presentation.resources.governance.state}
      data-command-center-motion={motionScene.activity}
      data-command-center-activity={motionScene.activity}
    >
      <section className="command-center-shell" aria-label="AI Review 指挥中心">
        <RuntimeHud
          presentation={presentation}
          loading={runtimeLoading}
        />

        <CommandCenterNotice
          presentation={presentation}
          loading={runtimeLoading}
          onRetryAll={reload}
          onRetryRuntime={reloadRuntime}
        />

        <CommandCenterCanvas
          presentation={presentation}
          motionScene={motionScene}
          runtimeLoading={runtimeLoading}
          onOpenReview={item => navigateTo(item.navigationTarget)}
          onOpenOverflow={openOverflow}
          onOpenResult={navigateTo}
        />

        <QualityOutput
          presentation={presentation}
          onRetryGovernance={reloadGovernance}
        />

        <p className="command-center-scope-note">
          顶部与执行拓扑展示 Runtime 当前状态；下方展示近 24 小时 Runtime / Governance 质量产出，资源异常或部分截断时会在对应区域提示。
        </p>
      </section>

      <Modal
        title={overflowLane ? `${overflowLane.title} · 运行中的审查` : '运行中的审查'}
        open={Boolean(overflowLane)}
        footer={null}
        width={720}
        onCancel={closeOverflow}
        afterClose={restoreOverflowFocus}
        keyboard
        destroyOnHidden
      >
        {overflowLane && (
          <RunningItemsModal
            lane={overflowLane}
            onOpenReview={item => navigateTo(item.navigationTarget)}
          />
        )}
      </Modal>
    </main>
  );
}


function RuntimeHud({ presentation, loading }) {
  const { currentStatus, agentLane, standardLane, resources } = presentation;
  const provider = currentStatus.provider;
  const queuedDetail = [
    `Agent ${agentLane.queued}`,
    `Standard ${standardLane.queued}`,
    currentStatus.oldestAgentQueueSeconds === null
      ? null
      : `Agent 最长等待 ${formatDuration(currentStatus.oldestAgentQueueSeconds)}`
  ].filter(Boolean).join(' · ');

  return (
    <section className="command-center-hud" aria-label="Runtime 当前摘要">
      <HudMetric
        icon="◷"
        label="Runtime 更新时间"
        value={formatSnapshotTime(currentStatus.generatedAt)}
        detail={loading && !currentStatus.generatedAt
          ? '正在获取首轮快照'
          : freshnessLabel(resources.runtime.state)}
        token="runtime"
      />
      <HudMetric
        icon="▤"
        label="排队执行数"
        value={displayMetric(currentStatus.queuedExecutionCount)}
        detail={currentStatus.available ? queuedDetail : runtimeUnavailableLabel(resources.runtime)}
        token="queued"
      />
      <HudMetric
        icon="▷"
        label="运行执行数"
        value={displayMetric(currentStatus.runningExecutionCount)}
        detail={currentStatus.available
          ? `Agent ${agentLane.running} · Standard ${standardLane.running}`
          : runtimeUnavailableLabel(resources.runtime)}
        token="running"
      />
      <HudMetric
        icon="◎"
        label="进行中审查任务"
        value={displayMetric(currentStatus.activeReviewTaskCount)}
        detail={currentStatus.available ? 'ReviewTask · 运行或审查中' : runtimeUnavailableLabel(resources.runtime)}
        token="active"
      />
      <HudMetric
        icon="⬡"
        label="当前 Provider / Model"
        value={currentStatus.available ? provider?.label || '暂无可观测 Provider' : '—'}
        detail={currentStatus.available
          ? presentation.hud.providersObserved.length > 1
            ? `另外 ${presentation.hud.providersObserved.length - 1} 个可观测项`
            : provider ? '当前或最近可观测' : '等待 Provider 执行记录'
          : runtimeUnavailableLabel(resources.runtime)}
        token="provider"
      />
    </section>
  );
}


function HudMetric({ icon, label, value, detail, token }) {
  return (
    <article className={`command-center-hud-card is-${token}`}>
      <span className="command-center-hud-icon" aria-hidden="true">{icon}</span>
      <span className="command-center-hud-copy">
        <small>{label}</small>
        <strong>{value}</strong>
        <em>{detail}</em>
      </span>
    </article>
  );
}


function RunningItemsModal({ lane, onOpenReview }) {
  const loaded = lane.runningItems.length;
  const total = lane.totalRunningItemCount;
  return (
    <div className="command-center-modal-content">
      <p className="command-center-modal-notice" role="status">
        当前列表来自 Runtime 有界快照，已载入 {loaded} / 共 {total} 条运行项。
        {lane.runningItemsTruncated ? ' 接口已标记为部分截断。' : ''}
      </p>
      <div className="command-center-modal-list">
        {loaded === 0 && (
          <p className="command-center-modal-empty">当前快照未返回可打开的运行中审查。</p>
        )}
        {lane.runningItems.map(item => (
          item.navigationTarget ? (
            <button
              key={item.motionIdentity}
              type="button"
              data-command-center-action="open-review-from-modal"
              onClick={() => onOpenReview(item)}
              aria-label={`打开 ${item.projectName} 的 ${item.displayName}`}
            >
              <span className={`command-center-modal-token is-${item.engineToken}`} aria-hidden="true" />
              <span>
                <strong>{item.projectName}</strong>
                <small>{item.displayName} · {item.providerModelLabel}</small>
              </span>
              <em>{item.stageLabel}</em>
            </button>
          ) : (
            <div key={item.motionIdentity} className="command-center-modal-item is-disabled">
              <span className={`command-center-modal-token is-${item.engineToken}`} aria-hidden="true" />
              <span>
                <strong>{item.projectName}</strong>
                <small>{item.displayName} · 任务标识不可用</small>
              </span>
              <em>{item.stageLabel}</em>
            </div>
          )
        ))}
      </div>
    </div>
  );
}


function CommandCenterNotice({ presentation, loading, onRetryAll, onRetryRuntime }) {
  const { hud, diagnostics, resources } = presentation;
  const runtime = resources.runtime;
  const governance = resources.governance;
  if (runtime.state === 'ERROR_EMPTY' && governance.state === 'ERROR_EMPTY') {
    return (
      <div className="command-center-notice is-error" role="alert">
        <strong>指挥中心数据暂时无法获取。</strong>
        <span>Runtime 与近 24 小时质量统计均加载失败。</span>
        <NoticeRetry onRetry={onRetryAll} label="重新加载" />
      </div>
    );
  }
  if (runtime.state === 'ERROR_RETAINED') {
    return (
      <div className="command-center-notice is-error" role="alert">
        <strong>Runtime 刷新失败，已保留最后一次成功快照。</strong>
        <span>{runtime.error}</span>
        <NoticeRetry onRetry={onRetryRuntime} label="重试 Runtime" />
      </div>
    );
  }
  if (runtime.state === 'ERROR_EMPTY') {
    return (
      <div className="command-center-notice is-error" role="alert">
        <strong>Runtime 快照暂不可用。</strong>
        <span>{runtime.error}</span>
        <NoticeRetry onRetry={onRetryRuntime} label="重试 Runtime" />
      </div>
    );
  }
  if (runtime.freshness === 'STALE') {
    return (
      <div className="command-center-notice is-stale" role="status">
        <strong>Runtime 已过期。</strong>
        <span>当前数据可能已过期，上次更新于 {formatSnapshotTime(runtime.generatedAt)}。</span>
      </div>
    );
  }
  if (runtime.freshness === 'EMPTY' && !loading) {
    return (
      <div className="command-center-notice" role="status">
        <strong>等待 Runtime 快照。</strong>
        <span>不会生成模拟任务、执行器或 Provider。</span>
      </div>
    );
  }
  if (hud.coverage.truncated || diagnostics.length > 0) {
    return (
      <div className="command-center-notice is-bounded" role="status">
        <strong>{hud.coverage.truncated ? 'Runtime 快照部分截断。' : 'Runtime 聚合需要对账。'}</strong>
        <span>{diagnostics.length > 0 ? '调度器总数与执行轨分布存在差异，页面分别保留真实字段。' : '运行项为有界结果。'}</span>
      </div>
    );
  }
  return null;
}


function QualityOutput({ presentation, onRetryGovernance }) {
  const { qualityOutput, resources } = presentation;
  const { reviewTasks, providerExecution, findingRisk, window } = qualityOutput;
  const providerVisual = providerQualityVisual(providerExecution);
  const findingVisual = findingSeverityVisual(findingRisk);
  const riskVisual = affectedRiskVisual(findingRisk);
  const bothUnavailable = resources.runtime.state === 'ERROR_EMPTY'
    && resources.governance.state === 'ERROR_EMPTY';
  return (
    <section
      className="command-center-quality"
      aria-label={`${window.label}质量产出`}
      data-command-center-runtime-state={resources.runtime.state}
      data-command-center-governance-state={resources.governance.state}
    >
      {!bothUnavailable && (
        <QualityResourceNotice
          resource={resources.governance}
          onRetry={onRetryGovernance}
        />
      )}
      <div className="command-center-quality-grid">
        <QualityMetric
          icon="▤"
          label={`${window.label}审查任务`}
          value={displayMetric(reviewTasks.count)}
          detail={qualityMetricDetail(
            resources.runtime,
            reviewTasks.count === 0 ? `${window.label}暂无记录` : 'ReviewTask 创建数'
          )}
          token="review"
          source="runtime"
          visual={{ type: 'signal' }}
        />
        <QualityMetric
          icon="◉"
          label="Provider 执行结果"
          value={providerExecution.available
            ? providerExecution.hasRecords
              ? `成功 ${providerExecution.successCount} / 失败 ${providerExecution.failureCount}`
              : '暂无执行记录'
            : '—'}
          detail={qualityMetricDetail(
            resources.runtime,
            providerExecution.hasRecords
              ? `成功率 ${formatPercent(providerExecution.successRate)}`
              : window.label
          )}
          token="provider-result"
          source="runtime"
          visual={{ type: 'provider', ...providerVisual }}
        />
        <QualityMetric
          icon="◇"
          label="发现问题数"
          value={displayMetric(findingRisk.findingCount)}
          detail={qualityMetricDetail(
            resources.governance,
            findingRisk.findingCount === 0 ? `${window.label}暂无记录` : 'Finding 总数'
          )}
          token="finding"
          source="governance"
          visual={{ type: 'finding', ...findingVisual }}
        />
        <QualityMetric
          icon="△"
          label="受影响任务"
          value={displayMetric(findingRisk.affectedTaskCount)}
          detail={qualityMetricDetail(
            resources.governance,
            findingRisk.affectedTaskCount === 0
              ? `${window.label}暂无记录`
              : `最高风险：${riskLabel(findingRisk.highestRisk)}`
          )}
          token="risk"
          source="governance"
          visual={{ type: 'risk', ...riskVisual }}
        />
      </div>
    </section>
  );
}


function QualityResourceNotice({ resource, onRetry }) {
  if (resource.state === 'ERROR_RETAINED') {
    return (
      <div className="command-center-quality-notice is-error" role="alert">
        <span>质量统计刷新失败，已保留上次数据 · {formatSnapshotMinute(resource.generatedAt)}</span>
        <NoticeRetry onRetry={onRetry} label="重试质量统计" />
      </div>
    );
  }
  if (resource.state === 'ERROR_EMPTY') {
    return (
      <div className="command-center-quality-notice is-error" role="alert">
        <span>质量统计暂时无法获取。</span>
        <NoticeRetry onRetry={onRetry} label="重试质量统计" />
      </div>
    );
  }
  if (resource.freshness === 'STALE') {
    return (
      <div className="command-center-quality-notice is-stale" role="status">
        质量统计可能已过期，上次更新于 {formatSnapshotTime(resource.generatedAt)}。
      </div>
    );
  }
  if (resource.truncated) {
    return (
      <div className="command-center-quality-notice is-stale" role="status">
        部分质量统计已截断，当前指标可能不完整。
      </div>
    );
  }
  return null;
}


function NoticeRetry({ onRetry, label }) {
  if (typeof onRetry !== 'function') return null;
  return (
    <button
      type="button"
      className="command-center-notice-action"
      onClick={onRetry}
    >
      {label}
    </button>
  );
}


function QualityMetric({ icon, label, value, detail, token, source, visual }) {
  return (
    <article
      className={`command-center-quality-card is-${token}`}
      data-command-center-source={source}
    >
      <span className="command-center-quality-icon" aria-hidden="true">{icon}</span>
      <span className="command-center-quality-copy">
        <small>{label}</small>
        <strong>{value}</strong>
        <em>{detail}</em>
      </span>
      <QualityMicroVisual visual={visual} />
    </article>
  );
}


function QualityMicroVisual({ visual }) {
  if (!visual) return null;
  if (visual.type === 'signal') {
    return (
      <span
        className="command-center-quality-visual is-signal"
        data-command-center-quality-visual="review-signal"
        aria-hidden="true"
      />
    );
  }
  if (visual.type === 'provider') {
    return (
      <span
        className="command-center-quality-visual is-provider"
        data-command-center-quality-visual="provider-breakdown"
        data-empty={visual.empty ? 'true' : 'false'}
        role="img"
        aria-label={visual.label}
      >
        <i className="is-success" style={{ '--cc-segment-share': `${visual.successPercent}%` }} />
        <i className="is-failure" style={{ '--cc-segment-share': `${visual.failurePercent}%` }} />
      </span>
    );
  }
  if (visual.type === 'finding') {
    return (
      <span
        className="command-center-quality-visual is-finding"
        data-command-center-quality-visual="finding-severity"
        data-empty={visual.empty ? 'true' : 'false'}
        role="img"
        aria-label={visual.label}
      >
        {visual.bars.map(bar => (
          <i
            key={bar.token}
            className={`is-${bar.token}`}
            style={{ '--cc-bar-level': `${bar.percent}%` }}
            title={`${bar.label} ${bar.count}`}
          />
        ))}
      </span>
    );
  }
  return (
    <span
      className={`command-center-quality-visual is-risk is-${visual.token}`}
      data-command-center-quality-visual="risk-level"
      data-empty={visual.empty ? 'true' : 'false'}
      role="img"
      aria-label={visual.label}
    >
      {[1, 2, 3, 4].map(level => (
        <i key={level} data-active={level <= visual.level ? 'true' : 'false'} />
      ))}
    </span>
  );
}


function freshnessLabel(value) {
  return {
    FRESH: 'Runtime 实时',
    STALE: 'Runtime 已过期',
    EMPTY: '等待 Runtime 快照',
    ERROR_RETAINED: '刷新失败 · 保留旧快照',
    ERROR_EMPTY: 'Runtime 暂不可用'
  }[value] || 'Runtime 状态未知';
}


function formatSnapshotTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(date);
}


function formatSnapshotMinute(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).format(date);
}


function formatDuration(value) {
  if (value === null || value === undefined) return '—';
  const seconds = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes > 0 ? `${minutes} 分 ${remainder} 秒` : `${remainder} 秒`;
}


function displayMetric(value) {
  return value === null || value === undefined ? '—' : value;
}


function runtimeUnavailableLabel(resource) {
  if (resource.loading) return '正在获取 Runtime';
  if (resource.state === 'ERROR_EMPTY') return 'Runtime 暂时无法获取';
  return '等待 Runtime 快照';
}


function qualityMetricDetail(resource, normalDetail) {
  if (!resource.available) {
    if (resource.loading) return '正在获取数据';
    if (resource.state === 'ERROR_EMPTY') return '暂时无法获取';
    return '等待快照';
  }
  if (resource.state === 'ERROR_RETAINED') {
    return `${normalDetail} · 上次数据 ${formatSnapshotMinute(resource.generatedAt)}`;
  }
  if (resource.freshness === 'STALE') {
    return `${normalDetail} · 数据可能已过期`;
  }
  return normalDetail;
}


function formatPercent(value) {
  if (value === null || value === undefined) return '—';
  return `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}%`;
}


function riskLabel(value) {
  return {
    CRITICAL: '严重',
    HIGH: '高',
    MAJOR: '高',
    MEDIUM: '中',
    MINOR: '中',
    LOW: '低',
    INFO: '提示'
  }[String(value || '').toUpperCase()] || '暂无';
}
