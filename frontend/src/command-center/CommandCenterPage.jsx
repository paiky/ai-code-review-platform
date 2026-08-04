import { useCallback, useMemo, useRef, useState } from 'react';
import { Modal } from 'antd';
import { useNavigate } from 'react-router-dom';

import CommandCenterCanvas from './CommandCenterCanvas.jsx';
import { restoreCommandCenterFocus } from './commandCenterInteractions.js';
import { buildCommandCenterPresentation } from './commandCenterPresentation.js';
import { commandCenterMotionState } from './commandCenterVisual.js';
import { useCommandCenterRuntimeSnapshot } from './useCommandCenterSnapshots.js';
import './commandCenter.css';


export default function CommandCenterPage() {
  const navigate = useNavigate();
  const [overflowZoneKey, setOverflowZoneKey] = useState(null);
  const overflowTriggerRef = useRef(null);
  const pageRef = useRef(null);
  const { runtime, runtimeLoading, runtimeError } = useCommandCenterRuntimeSnapshot();
  const presentation = useMemo(
    () => buildCommandCenterPresentation({ runtime, runtimeError }),
    [runtime, runtimeError]
  );
  const motionState = commandCenterMotionState(presentation, runtimeLoading);
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
      data-command-center-phase="HOMEPAGE_VNEXT_H5"
      data-command-center-resource-state={presentation.hud.resourceState}
      data-command-center-motion={motionState}
    >
      <section className="command-center-shell" aria-label="AI Review 指挥中心">
        <RuntimeHud
          presentation={presentation}
          loading={runtimeLoading}
          onNavigate={navigateTo}
        />

        <RuntimeNotice
          presentation={presentation}
          loading={runtimeLoading}
        />

        <CommandCenterCanvas
          presentation={presentation}
          runtimeLoading={runtimeLoading}
          onOpenReview={item => navigateTo(item.navigationTarget)}
          onOpenOverflow={openOverflow}
          onOpenResult={navigateTo}
        />

        <RuntimeFooter presentation={presentation} />

        <p className="command-center-scope-note">
          当前页面展示 Runtime 实时有界快照；运行项与告警列表可能受接口上限影响。
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


function RuntimeHud({ presentation, loading, onNavigate }) {
  const { hud, agentLane, standardLane } = presentation;
  const provider = hud.providersObserved[0];
  const alert = hud.alerts.find(item => item.navigationTarget) || hud.alerts[0];
  const coverageDetail = hud.coverage.truncated
    ? '有界快照 · 部分截断'
    : '有界快照';

  return (
    <section className="command-center-hud" aria-label="Runtime 当前摘要">
      <HudMetric
        icon="◷"
        label="Runtime 更新时间"
        value={formatSnapshotTime(hud.generatedAt)}
        detail={loading && !hud.generatedAt ? '正在获取首轮快照' : freshnessLabel(hud.resourceState)}
        token="runtime"
      />
      <HudMetric
        icon="▤"
        label="排队任务总数"
        value={hud.totalQueuedJobs}
        detail={`Agent ${agentLane.queued} · Standard ${standardLane.queued}`}
        token="queued"
      />
      <HudMetric
        icon="▷"
        label="运行任务总数"
        value={hud.totalRunningJobs}
        detail={`Agent ${agentLane.running} · Standard ${standardLane.running}`}
        token="running"
      />
      <HudMetric
        icon="◇"
        label="快照覆盖范围"
        value={coverageLabel(hud.coverage)}
        detail={coverageDetail}
        token={hud.coverage.truncated ? 'warning' : 'coverage'}
      />
      <HudMetric
        icon="⬡"
        label="已观测 Provider / Model"
        value={provider?.label || '暂无活跃 Provider'}
        detail={hud.providersObserved.length > 1 ? `另外 ${hud.providersObserved.length - 1} 个` : '当前活动流程观测'}
        token="provider"
      />
      <HudMetric
        icon="△"
        label="Runtime 告警"
        value={`${hud.alerts.length} 条告警`}
        detail={alert ? alertLabel(alert) : '当前无 Runtime 告警'}
        token={hud.alerts.length > 0 ? 'alert' : 'neutral'}
        actionLabel={alert?.navigationTarget ? `打开 ${alertLabel(alert)}` : null}
        onAction={alert?.navigationTarget ? () => onNavigate(alert.navigationTarget) : null}
      />
    </section>
  );
}


function HudMetric({ icon, label, value, detail, token, actionLabel, onAction }) {
  const content = (
    <>
      <span className="command-center-hud-icon" aria-hidden="true">{icon}</span>
      <span className="command-center-hud-copy">
        <small>{label}</small>
        <strong>{value}</strong>
        <em>{detail}</em>
      </span>
    </>
  );
  if (onAction) {
    return (
      <button
        type="button"
        className={`command-center-hud-card is-${token} is-actionable`}
        data-command-center-action="open-alert"
        aria-label={actionLabel}
        onClick={onAction}
      >
        {content}
      </button>
    );
  }
  return <article className={`command-center-hud-card is-${token}`}>{content}</article>;
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


function RuntimeNotice({ presentation, loading }) {
  const { hud, diagnostics } = presentation;
  if (hud.resourceState === 'ERROR_RETAINED') {
    return (
      <div className="command-center-notice is-error" role="alert">
        <strong>Runtime 刷新失败，已保留最后一次成功快照。</strong>
        <span>{hud.error}</span>
      </div>
    );
  }
  if (hud.resourceState === 'ERROR_EMPTY') {
    return (
      <div className="command-center-notice is-error" role="alert">
        <strong>Runtime 快照暂不可用。</strong>
        <span>{hud.error}</span>
      </div>
    );
  }
  if (hud.freshness === 'STALE') {
    return (
      <div className="command-center-notice is-stale" role="status">
        <strong>Runtime 已过期。</strong>
        <span>页面保留最近快照，当前数据可能不是最新状态。</span>
      </div>
    );
  }
  if (hud.freshness === 'EMPTY' && !loading) {
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
        <span>{diagnostics.length > 0 ? '调度器总数与执行轨分布存在差异，页面分别保留真实字段。' : '运行项与告警为有界结果。'}</span>
      </div>
    );
  }
  return null;
}


function RuntimeFooter({ presentation }) {
  const { footer } = presentation;
  return (
    <section className="command-center-footer" aria-label="Runtime 当前状态">
      <FooterMetric
        icon="◎"
        label="Agent 容量"
        value={`${footer.agentCapacity.running} / ${footer.agentCapacity.onlineCapacity || '—'}`}
        detail="运行中 / 在线容量"
        ratio={safeRatio(footer.agentCapacity.running, footer.agentCapacity.onlineCapacity)}
        token="agent"
      />
      <FooterMetric
        icon="▥"
        label="Standard Provider 槽位"
        value={`${footer.standardSlots.running} / ${footer.standardSlots.capacity || '—'}`}
        detail="运行中 / 总容量"
        ratio={safeRatio(footer.standardSlots.running, footer.standardSlots.capacity)}
        token="standard"
      />
      <FooterMetric
        icon="◷"
        label="Agent 最长排队等待"
        value={formatDuration(footer.oldestAgentQueueSeconds)}
        detail={footer.oldestAgentQueueSeconds === null ? '当前无可观测等待时长' : '当前最久排队'}
        token="wait"
      />
      <FooterMetric
        icon="△"
        label="Runtime 告警"
        value={footer.alerts.count}
        detail={footer.alerts.count > 0 ? alertLabel(footer.alerts.items[0]) : '当前无告警'}
        token={footer.alerts.count > 0 ? 'alert' : 'neutral'}
      />
    </section>
  );
}


function FooterMetric({ icon, label, value, detail, ratio, token }) {
  return (
    <article className={`command-center-footer-card is-${token}`}>
      <span className="command-center-footer-icon" aria-hidden="true">{icon}</span>
      <span>
        <small>{label}</small>
        <strong>{value}</strong>
        {typeof ratio === 'number' && (
          <i className="command-center-meter" aria-hidden="true">
            <b style={{ width: `${ratio}%` }} />
          </i>
        )}
        <em>{detail}</em>
      </span>
    </article>
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


function coverageLabel(coverage) {
  if (coverage.status === 'EMPTY') return '等待快照';
  return coverage.truncated ? '部分截断' : '未截断';
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


function formatDuration(value) {
  if (value === null || value === undefined) return '—';
  const seconds = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes > 0 ? `${minutes} 分 ${remainder} 秒` : `${remainder} 秒`;
}


function safeRatio(value, capacity) {
  if (!capacity) return null;
  return Math.min(100, Math.round((value / capacity) * 100));
}


function alertLabel(alert) {
  const typeLabel = {
    JOB_FAILED: '任务失败',
    AGENT_RUN_FAILED: 'Agent 执行失败',
    NOTIFICATION_FAILED: '通知失败',
    FALLBACK: '发生降级',
    CRITICAL_FINDING: '发现严重问题',
    WORKER_OFFLINE: '执行器离线',
    WORKER_DRAINING: '执行器退出中'
  }[alert?.type] || '其他告警';
  return [alert?.projectName, typeLabel].filter(Boolean).join(' · ') || 'Runtime 告警';
}
