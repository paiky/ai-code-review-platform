import { useLayoutEffect, useRef, useState } from 'react';

import { observeCommandCenterTopology } from './commandCenterTopology.js';


const EMPTY_TOPOLOGY = Object.freeze({ ready: false, width: 0, height: 0, paths: [] });


export default function CommandCenterCanvas({
  presentation,
  runtimeLoading,
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
    todayResults
  } = presentation;

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
      data-command-center-animation-owner="STATIC_M2_1"
      data-command-center-topology-ready={topology.ready ? 'true' : 'false'}
    >
      <StaticConnections topology={topology} />

      <div className="command-center-mobile-route-summary" role="note">
        <strong>审查路由</strong>
        <span>任务队列 → 引擎选择 → Agent Review 或 Standard Review → 审查结果</span>
      </div>

      <div className="command-center-map-grid">
        <ReviewTaskQueue taskQueue={taskQueue} onOpenReview={onOpenReview} />
        <EngineSelection engineSelection={engineSelection} />
        <ReviewModule
          lane={agentLane}
          runtimeLoading={runtimeLoading}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
        />
        <FallbackRelation fallback={fallback} />
        <ReviewModule
          lane={standardLane}
          runtimeLoading={runtimeLoading}
          onOpenReview={onOpenReview}
          onOpenOverflow={onOpenOverflow}
        />
        <TodayReviewResults todayResults={todayResults} onOpen={onOpenResult} />
      </div>
    </section>
  );
}


function StaticConnections({ topology }) {
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
        <ConnectionMarker id="cc-arrow-fallback" color="#08a9b9" />
      </defs>
      {topology.paths.map(path => (
        <g
          key={path.id}
          className={`command-center-cable is-${path.token}`}
          data-command-center-connection-group={path.id}
          data-command-center-route-kind={path.kind}
        >
          <path className="command-center-connection is-glow" d={path.d} />
          <path className="command-center-connection is-rail" d={path.d} />
          <path
            className="command-center-connection is-core"
            data-command-center-connection={path.id}
            d={path.d}
            markerEnd={marker(path.token)}
          />
        </g>
      ))}
    </svg>
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


function EngineSelection({ engineSelection }) {
  return (
    <article
      className="command-center-engine command-center-map-node"
      data-zone-key={engineSelection.zoneKey}
      data-command-center-map-node="true"
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
        <NodeHeading eyebrow="策略路由" title={engineSelection.title} subtitle="可用性检查 · 安全门禁" />
        <div className="command-center-engine-routes">
          {engineSelection.routes.map(route => (
            <span key={route.key} className={`is-${route.token}`}>
              <i aria-hidden="true" />
              {route.label}
            </span>
          ))}
        </div>
      </div>
    </article>
  );
}


function ReviewModule({ lane, runtimeLoading, onOpenReview, onOpenOverflow }) {
  const isAgent = lane.engine === 'AGENT';
  const nextQueued = lane.nextQueued;
  const observedProvider = lane.providers[0];
  return (
    <article
      className={`command-center-review-module is-${lane.colorToken} command-center-map-node`}
      data-zone-key={lane.zoneKey}
      data-running={lane.running > 0 ? 'true' : 'false'}
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
      <header>
        <span className="command-center-module-icon" aria-hidden="true">{isAgent ? '⌘' : '▤'}</span>
        <span>
          <small>{lane.eyebrow}</small>
          <h2>{lane.title}</h2>
          <p>{lane.description}</p>
        </span>
        <em><i aria-hidden="true" />{runtimeLoading ? '同步中' : '当前快照'}</em>
      </header>

      <div className="command-center-module-metrics">
        <ModuleMetric label="排队任务" value={lane.queued} />
        <ModuleMetric label="运行任务" value={lane.running} />
        {isAgent ? (
          <ModuleMetric label="在线容量" value={lane.onlineCapacity || '—'} />
        ) : (
          <ModuleMetric label="Provider 槽位" value={`${lane.running} / ${lane.capacity || '—'}`} />
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
    </article>
  );
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


function FallbackRelation({ fallback }) {
  return (
    <aside className="command-center-fallback" aria-label="Agent 到 Standard 的结构性降级关系">
      <strong>Agent Review → Standard Review</strong>
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
