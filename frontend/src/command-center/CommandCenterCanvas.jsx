import { useLayoutEffect, useRef, useState } from 'react';

import { observeCommandCenterTopology } from './commandCenterTopology.js';


const EMPTY_TOPOLOGY = Object.freeze({ ready: false, width: 0, height: 0, paths: [] });


export default function CommandCenterCanvas({
  presentation,
  motionScene,
  runtimeLoading,
  preview,
  onOpenReview,
  onOpenOverflow,
  onOpenResult
}) {
  const mapRef = useRef(null);
  const [topology, setTopology] = useState(EMPTY_TOPOLOGY);
  const {
    taskQueue,
    engineSelection,
    agentLane,
    standardLane,
    fallback,
    todayResults,
    resources
  } = presentation;
  const runtimeState = resources.runtime.state;

  useLayoutEffect(() => {
    if (!mapRef.current) return undefined;
    const owner = observeCommandCenterTopology(mapRef.current, setTopology);
    return () => owner.disconnect();
  }, []);

  return (
    <section
      ref={mapRef}
      className="command-center-runtime-map"
      aria-label="AI Review 当前执行拓扑"
      data-command-center-renderer="DOM_SVG_LIVE_TOPOLOGY"
      data-command-center-canvas-mounted="false"
      data-command-center-dom-fallback="always"
      data-command-center-animation-owner="CSS_STATE_M3"
      data-command-center-activity={motionScene.activity}
      data-command-center-topology-ready={topology.ready ? 'true' : 'false'}
    >
      <PreviewToolbar preview={preview} />
      <StaticConnections topology={topology} motionScene={motionScene} />

      <MobileRouteSummary motionScene={motionScene} runtimeState={runtimeState} preview={preview} />

      <div className="command-center-map-grid">
        <ReviewTaskQueue taskQueue={taskQueue} onOpenReview={onOpenReview} />
        <EngineSelection engineSelection={engineSelection} activity={motionScene.activity} />
        <ReviewModule
          lane={agentLane}
          motionLane={motionScene.lanes.agent}
          runtimeLoading={runtimeLoading}
          runtimeState={runtimeState}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
          fallback={fallback}
          fallbackActive={motionScene.fallbackActive}
        />
        <ResponsiveHandoffDivider fallbackActive={motionScene.fallbackActive} />
        <ReviewModule
          lane={standardLane}
          motionLane={motionScene.lanes.standard}
          runtimeLoading={runtimeLoading}
          runtimeState={runtimeState}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
          fallbackActive={motionScene.fallbackActive}
        />
        <TodayReviewResults todayResults={todayResults} onOpen={onOpenResult} />
      </div>
    </section>
  );
}


function PreviewToolbar({ preview }) {
  return (
    <div
      className="command-center-preview-toolbar"
      data-command-center-preview-state={preview.phase || 'IDLE'}
    >
      <PreviewControl preview={preview} />
    </div>
  );
}


function PreviewControl({ preview }) {
  return (
    <span className="command-center-preview-control">
      {preview.active && (
        <span className="command-center-preview-badge" role="status">
          演示 · {preview.phaseLabel}
        </span>
      )}
      <button
        type="button"
        className="command-center-preview-button"
        data-command-center-action="preview-review-motion"
        disabled={!preview.enabled || preview.active}
        title={preview.enabled ? '预览 Agent 优先与 Standard 降级动画' : '仅 Runtime 实时且当前空闲时可预览'}
        onClick={preview.onStart}
      >
        <span aria-hidden="true">▷</span>
        {preview.active ? '预览中' : '预览动画'}
      </button>
    </span>
  );
}


function MobileRouteSummary({ motionScene, runtimeState, preview }) {
  const status = mobileRouteStatus(motionScene, runtimeState);
  return (
    <div
      className="command-center-mobile-route-summary"
      role="note"
      data-runtime-state={runtimeState}
      data-agent-activity={motionScene.lanes.agent.activity}
      data-standard-activity={motionScene.lanes.standard.activity}
      data-fallback-active={motionScene.fallbackActive ? 'true' : 'false'}
    >
      <strong>Agent 优先审查路由</strong>
      <span>任务队列 → Agent Review 主通道 → 审查结果；异常时由 Standard Review 接管</span>
      <em>{status}</em>
      <span className="command-center-mobile-route-actions">
        <PreviewControl preview={preview} />
      </span>
    </div>
  );
}


function mobileRouteStatus(motionScene, runtimeState) {
  if (runtimeState === 'ERROR_RETAINED') return '刷新失败，保留旧快照 · 动效已暂停';
  if (runtimeState === 'STALE') return 'Runtime 快照已过期 · 动效已暂停';
  if (runtimeState === 'ERROR_EMPTY') return 'Runtime 暂不可用';
  if (runtimeState === 'EMPTY') return '等待 Runtime 快照';
  if (motionScene.fallbackActive) return 'Agent 异常 · Standard 正在兜底';
  if (motionScene.lanes.agent.running) return 'Agent 主通道运行中';
  if (motionScene.lanes.agent.queued) return 'Agent 主通道排队中';
  if (motionScene.lanes.standard.running) return 'Standard 备用通道运行中';
  if (motionScene.lanes.standard.queued) return 'Standard 备用通道排队中';
  return motionScene.activity === 'paused' ? '线路动效已暂停' : '当前空闲';
}


function StaticConnections({ topology, motionScene }) {
  const marker = token => `url(#cc-arrow-${token})`;
  return (
    <svg
      className="command-center-static-connections"
      viewBox={`0 0 ${topology.width || 1} ${topology.height || 1}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
      data-command-center-connections-ready={topology.ready ? 'true' : 'false'}
    >
      <defs>
        <ConnectionMarker id="cc-arrow-intake" color="#2787f5" />
        <ConnectionMarker id="cc-arrow-agent" color="#6f3df4" />
        <ConnectionMarker id="cc-arrow-standard" color="#f07818" />
        <ConnectionMarker id="cc-arrow-fallback" color="#f07818" />
      </defs>
      {topology.paths.map(path => {
        const state = motionScene.connections[path.id] || { activity: 'idle', active: false };
        const fallbackActive = path.id === 'agent-standard' && motionScene.fallbackActive;
        return (
          <g
            key={path.id}
            className={`command-center-cable is-${path.token}`}
            data-command-center-connection-group={path.id}
            data-command-center-route-kind={path.kind}
            data-active={state.active ? 'true' : 'false'}
            data-flow-state={state.activity}
            data-fallback-active={fallbackActive ? 'true' : 'false'}
          >
            <path className="command-center-connection is-glow" d={path.d} pathLength="100" />
            <path className="command-center-connection is-rail" d={path.d} pathLength="100" />
            <path
              className="command-center-connection is-core"
              data-command-center-connection={path.id}
              d={path.d}
              pathLength="100"
              markerEnd={marker(path.token)}
            />
            <path className="command-center-connection command-center-flow" d={path.d} pathLength="100" />
            <path className="command-center-connection command-center-pulse" d={path.d} pathLength="100" />
            {path.kind === 'fallback' && path.midpoint && (
              <FallbackHandoffNode midpoint={path.midpoint} active={fallbackActive} />
            )}
          </g>
        );
      })}
    </svg>
  );
}


function FallbackHandoffNode({ midpoint, active }) {
  return (
    <g
      className="command-center-fallback-handoff"
      transform={`translate(${midpoint.x} ${midpoint.y})`}
      data-command-center-fallback-handoff="desktop"
      data-active={active ? 'true' : 'false'}
    >
      <circle className="command-center-fallback-handoff-halo" r="28" />
      <circle className="command-center-fallback-handoff-surface" r="24" />
      <path className="command-center-fallback-handoff-chevron" d="M -8 -8 L 0 0 L 8 -8" />
      <path className="command-center-fallback-handoff-chevron" d="M -8 1 L 0 9 L 8 1" />
      <text className="command-center-fallback-handoff-label" x="0" y="42">降级通道</text>
    </g>
  );
}


function ResponsiveHandoffDivider({ fallbackActive }) {
  return (
    <div
      className="command-center-responsive-handoff"
      role="note"
      aria-label="Agent Review 异常时降级至 Standard Review"
      data-command-center-fallback-handoff="responsive"
      data-active={fallbackActive ? 'true' : 'false'}
    >
      <span aria-hidden="true"><i /><i /></span>
      <small>异常降级至 Standard Review</small>
    </div>
  );
}


function ConnectionMarker({ id, color }) {
  return (
    <marker id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4.5" markerHeight="4.5" orient="auto">
      <path d="M 1 1 L 9 5 L 1 9" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </marker>
  );
}


function ReviewTaskQueue({ taskQueue, onOpenReview }) {
  const countLabel = taskQueue.available
    ? `展示 ${taskQueue.visibleCount} / 活动 ${taskQueue.activeCount}`
    : '任务数据暂不可用';
  return (
    <article
      className="command-center-intake command-center-task-queue command-center-map-node"
      data-zone-key={taskQueue.zoneKey}
      data-command-center-map-node="true"
    >
      <ConnectionPort id="queue-out" token="intake" position="right" />
      <NodeHeading icon="▤" eyebrow={taskQueue.eyebrow} title={taskQueue.title} subtitle={taskQueue.subtitle} />
      <strong className="command-center-task-count">{countLabel}</strong>
      <div className="command-center-task-list">
        {!taskQueue.available ? (
          <p className="command-center-side-empty">Runtime 当前不可用</p>
        ) : taskQueue.items.length === 0 ? (
          <p className="command-center-side-empty">当前无活动 ReviewTask</p>
        ) : taskQueue.items.map(item => (
          <ReviewTaskItem key={item.taskId || `${item.projectName}:${item.updatedAt}`} item={item} onOpen={onOpenReview} />
        ))}
      </div>
      {taskQueue.overflowCount > 0 && (
        <small className="command-center-task-overflow">另有 {taskQueue.overflowCount} 项活动任务</small>
      )}
    </article>
  );
}


function ReviewTaskItem({ item, onOpen }) {
  return (
    <section className="command-center-task-item">
      <div className="command-center-task-primary">
        <strong title={item.projectName}>{item.projectName}</strong>
        <span className="command-center-task-trigger">{item.triggerLabel}</span>
      </div>
      <span className="command-center-task-author">作者：{item.authorLabel}</span>
      <span className="command-center-task-ref" title={item.branchCommitLabel}>{item.branchCommitLabel}</span>
      <span className="command-center-task-state">
        <b>{item.stageLabel}</b>
        <time dateTime={item.updatedAt || undefined}>{formatRelativeTime(item.updatedAt)}</time>
      </span>
      <span className="command-center-task-actions">
        {item.navigationTarget && (
          <button type="button" onClick={() => onOpen(item)} data-command-center-action="open-queued-review">
            查看任务
          </button>
        )}
        {item.externalUrl && (
          <a href={item.externalUrl} target="_blank" rel="noopener noreferrer">
            打开 GitLab
          </a>
        )}
      </span>
    </section>
  );
}


function EngineSelection({ engineSelection, activity }) {
  return (
    <article
      className="command-center-engine command-center-map-node"
      data-zone-key={engineSelection.zoneKey}
      data-command-center-map-node="true"
      data-activity={activity}
    >
      <div className="command-center-engine-ring" aria-hidden="true">
        <ConnectionPort id="engine-in" token="intake" position="orbit-left" />
        <ConnectionPort id="engine-agent-out" token="agent" position="orbit-right-upper" />
        <ConnectionPort id="engine-standard-out" token="standard" position="orbit-right-lower" />
        <span className="command-center-engine-orbit is-outer"><i /></span>
        <span className="command-center-engine-orbit is-main"><i /></span>
        <span className="command-center-engine-orbit is-inner"><i /></span>
        <span className="command-center-engine-core"><b>AI</b></span>
        <i className="command-center-engine-node is-node-one" />
        <i className="command-center-engine-node is-node-two" />
        <i className="command-center-engine-node is-node-three" />
      </div>
      <div className="command-center-engine-panel">
        <NodeHeading eyebrow="策略路由" title={engineSelection.title} subtitle={engineSelection.subtitle} />
      </div>
    </article>
  );
}


function ReviewModule({
  lane,
  motionLane,
  runtimeLoading,
  runtimeState,
  onOpenReview,
  onOpenOverflow,
  fallback = null,
  fallbackActive = false
}) {
  const isAgent = lane.engine === 'AGENT';
  const nextQueued = lane.nextQueued;
  const observedProvider = lane.providers[0];
  const statusLabel = reviewModuleStatus({ lane, motionLane, runtimeLoading, runtimeState });
  return (
    <article
      className={`command-center-review-module is-${lane.colorToken} is-${lane.role} command-center-map-node`}
      data-zone-key={lane.zoneKey}
      data-review-role={lane.role}
      data-queued={lane.queued > 0 ? 'true' : 'false'}
      data-running={lane.running > 0 ? 'true' : 'false'}
      data-activity={motionLane.activity}
      data-runtime-state={runtimeState}
      data-fallback-active={fallbackActive ? 'true' : 'false'}
      data-command-center-map-node="true"
    >
      {isAgent ? (
        <>
          <ConnectionPort id="agent-in" token="agent" position="left" />
          <ConnectionPort id="agent-out" token="agent" position="right" />
          <ConnectionPort id="agent-down" token="fallback" position="bottom" />
        </>
      ) : (
        <>
          <ConnectionPort id="standard-in" token="standard" position="left" />
          <ConnectionPort id="standard-out" token="standard" position="right" />
          <ConnectionPort id="standard-up" token="fallback" position="top" />
        </>
      )}
      <span className="command-center-review-neon" aria-hidden="true" />
      <header>
        <span className="command-center-module-icon" aria-hidden="true">{isAgent ? '⌘' : '▤'}</span>
        <span className="command-center-module-copy">
          <span className="command-center-module-title-row">
            <h2>{lane.title}</h2>
            <strong className="command-center-module-role">{lane.roleLabel}</strong>
            {lane.supportLabel && (
              <small className="command-center-module-support">{lane.supportLabel}</small>
            )}
          </span>
          <p>{lane.description}</p>
        </span>
        <em data-runtime-status={statusLabel}>
          <i aria-hidden="true" />
          {statusLabel}
        </em>
      </header>

      <div className="command-center-module-metrics" data-review-metric-layout={lane.role}>
        <ModuleMetric label="排队任务" value={lane.queued} />
        <ModuleMetric label="运行任务" value={lane.running} />
        {isAgent ? (
          <ModuleMetric label="在线容量" value={lane.available ? lane.onlineCapacity : '—'} />
        ) : (
          <ModuleMetric
            label="Provider 槽位"
            value={lane.available ? `${lane.running} / ${lane.capacity}` : '—'}
          />
        )}
        {isAgent ? (
          <WorkerSummary summary={lane.workerSummary} />
        ) : (
          <ModuleMetric
            label="已观测 Provider / Model"
            value={observedProvider?.label || '暂无可观测 Provider'}
            compact
          />
        )}
        <ModuleMetric
          label="下一排队任务"
          value={nextQueued ? nextQueued.displayName : '当前无等待任务'}
          detail={nextQueued ? nextQueued.projectName : null}
          compact
        />
        <RunningItems
          lane={lane}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
        />
      </div>
      {isAgent && fallback && (
        <AgentPriorityStrategy fallback={fallback} active={fallbackActive} />
      )}
    </article>
  );
}


function reviewModuleStatus({ lane, motionLane, runtimeLoading, runtimeState }) {
  if (runtimeLoading) return lane.available ? '刷新中' : '同步中';
  if (runtimeState === 'ERROR_RETAINED') return '保留旧状态';
  if (runtimeState === 'STALE') return '快照已过期';
  if (!lane.available) return '数据不可用';
  if (motionLane.running) return '运行中';
  if (motionLane.queued) return '排队中';
  if (lane.engine === 'AGENT') {
    return lane.onlineCapacity > 0 ? '有在线执行器' : '暂无在线执行器';
  }
  if (lane.capacity > lane.running) return '有可用槽位';
  return lane.capacity > 0 ? '槽位已满' : '暂无可用槽位';
}


function ModuleMetric({ label, value, detail, compact = false }) {
  return (
    <div className={`command-center-module-metric${compact ? ' is-compact' : ''}`}>
      <small>{label}</small>
      <strong>{value}</strong>
      {detail && <em>{detail}</em>}
    </div>
  );
}


function WorkerSummary({ summary }) {
  const rows = [
    ['IDLE', '空闲', summary?.idle || 0],
    ['BUSY', '忙碌', summary?.busy || 0],
    ['DRAINING', '退出中', summary?.draining || 0],
    ['OFFLINE', '离线', summary?.offline || 0]
  ];
  return (
    <div className="command-center-module-metric is-worker-summary">
      <small>执行器概览</small>
      <span>
        {rows.map(([state, label, value]) => (
          <i key={state} className={`is-${state.toLowerCase()}`}>
            <b aria-hidden="true" />{label}<em>{value}</em>
          </i>
        ))}
      </span>
    </div>
  );
}


function RunningItems({ lane, onOpenReview, onOpenOverflow }) {
  const visibleItems = lane.runningItems.slice(0, 4);
  const visible = visibleItems.length;
  const total = lane.totalRunningItemCount;
  const hasOverflow = lane.runningItems.length > visible
    || lane.runningItemsTruncated
    || total > visible;
  return (
    <div className="command-center-module-metric is-running-items">
      <small>运行项</small>
      <strong>显示 {visible} / 共 {total}</strong>
      <span className="command-center-running-markers" aria-label={`当前展示 ${visible} 个，共 ${total} 个运行项`}>
        {visibleItems.map(item => (
          item.navigationTarget ? (
            <button
              key={item.motionIdentity}
              type="button"
              className="command-center-running-marker"
              data-command-center-action="open-running-review"
              data-review-identity={item.motionIdentity}
              title={`${item.projectName} · ${item.displayName} · ${item.stageLabel}`}
              aria-label={`打开 ${item.projectName} 的 ${item.displayName}`}
              onClick={() => onOpenReview(item)}
            />
          ) : (
            <i key={item.motionIdentity} className="command-center-running-marker is-disabled" />
          )
        ))}
      </span>
      {hasOverflow && (
        <button
          type="button"
          className="command-center-running-overflow"
          data-command-center-action={`open-${lane.engine.toLowerCase()}-overflow`}
          onClick={event => onOpenOverflow(lane, event.currentTarget)}
          aria-label={`查看 ${lane.title} 运行项列表`}
        >
          查看运行项
        </button>
      )}
    </div>
  );
}


function AgentPriorityStrategy({ fallback, active }) {
  return (
    <aside
      className="command-center-agent-strategy"
      aria-label="Agent 优先策略"
      data-fallback-active={active ? 'true' : 'false'}
    >
      <strong>{fallback.title}</strong>
      <span>{fallback.description}</span>
    </aside>
  );
}


function TodayReviewResults({ todayResults, onOpen }) {
  const metrics = todayResults.available ? [
    ['success', '成功', todayResults.successCount],
    ['failure', '失败', todayResults.failureCount],
    ['skipped', '跳过', todayResults.skippedCount],
    ['running', '进行中', todayResults.runningCount]
  ] : [];
  return (
    <article
      className="command-center-result command-center-today-results command-center-map-node"
      data-zone-key={todayResults.zoneKey}
      data-command-center-map-node="true"
    >
      <ConnectionPort id="result-agent-in" token="agent" position="left-upper" />
      <ConnectionPort id="result-standard-in" token="standard" position="left-lower" />
      <span className="command-center-result-badge" aria-hidden="true">✓</span>
      <NodeHeading eyebrow={todayResults.eyebrow} title={todayResults.title} subtitle={todayResults.subtitle} />
      {todayResults.available ? (
        <>
          <strong className="command-center-result-total">完成 {todayResults.completedCount}</strong>
          <div className="command-center-result-metrics">
            {metrics.map(([token, label, value]) => (
              <span key={token} className={`is-${token}`}>
                <small>{label}</small>
                <b>{value}</b>
              </span>
            ))}
          </div>
          <p>共 {todayResults.totalCount} 个 Result</p>
          {todayResults.otherCount > 0 && (
            <small className="command-center-result-other">其他状态 {todayResults.otherCount}</small>
          )}
        </>
      ) : (
        <p className="command-center-side-empty">今日结果暂不可用</p>
      )}
      <button
        type="button"
        className="command-center-result-route"
        data-command-center-action="open-review-tasks"
        onClick={() => onOpen(todayResults.navigationTarget)}
      >
        查看审查任务 <span aria-hidden="true">→</span>
      </button>
    </article>
  );
}


function ConnectionPort({ id, token, position }) {
  return (
    <i
      className={`command-center-port is-${token} is-${position}`}
      data-command-center-port={id}
      aria-hidden="true"
    />
  );
}


function NodeHeading({ icon = null, eyebrow, title, subtitle }) {
  return (
    <header className="command-center-node-heading">
      {icon && <span className="command-center-node-heading-icon" aria-hidden="true">{icon}</span>}
      <small>{eyebrow}</small>
      <h2>{title}</h2>
      <p>{subtitle}</p>
    </header>
  );
}


function formatRelativeTime(value) {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return '更新时间未知';
  const seconds = Math.max(Math.floor((Date.now() - timestamp) / 1000), 0);
  if (seconds < 60) return '刚刚更新';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}
