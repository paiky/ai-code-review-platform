import { useCallback, useEffect, useMemo, useState } from 'react';
import { Modal } from 'antd';
import { useNavigate } from 'react-router-dom';

import CommandCenterCanvas from './CommandCenterCanvas.jsx';
import { buildCommandCenterPresentation } from './commandCenterPresentation.js';
import { useCommandCenterRuntimeSnapshot } from './useCommandCenterSnapshots.js';
import './commandCenter.css';


export default function CommandCenterPage() {
  const navigate = useNavigate();
  const [overflowLane, setOverflowLane] = useState(null);
  const visibleLimit = useRunningItemLimit();
  const { runtime, runtimeLoading, runtimeError, reload } = useCommandCenterRuntimeSnapshot();
  const presentation = useMemo(() => buildCommandCenterPresentation({ runtime }), [runtime]);
  const openReview = useCallback(item => {
    const reviewKey = encodeURIComponent(item.reviewKey || 'default');
    navigate(`/tasks/${item.taskId}?reviewKey=${reviewKey}`);
  }, [navigate]);
  const freshness = runtime?.freshness || (runtimeLoading ? 'LOADING' : 'EMPTY');

  return (
    <main className="command-center-page" data-command-center-phase="PHASE_5A">
      <section className="command-center-map-shell" aria-labelledby="command-center-title">
        <header className="command-center-map-toolbar">
          <div className="command-center-map-identity">
            <span className="command-center-kicker">AI REVIEW COMMAND CENTER</span>
            <h1 id="command-center-title">平台 Review 运行地图</h1>
          </div>
          <div className="command-center-snapshot-state" aria-live="polite">
            <span className={`command-center-status-dot is-${freshness.toLowerCase()}`} aria-hidden="true" />
            <span>
              <strong>{freshnessLabel(freshness)}</strong>
              <small>{formatSnapshotTime(runtime?.generatedAt)}</small>
            </span>
          </div>
          <HudMetric label="平台负载" value={`${presentation.hud.utilizationPercent}%`} detail={`${presentation.hud.totalRunning}/${presentation.hud.totalCapacity || '—'}`} />
          <HudMetric label="运行中" value={presentation.hud.totalRunning} detail="Standard + Agent" />
          <HudMetric label="前方等待" value={presentation.hud.totalQueued} detail="双路线合计" token="queue" />
          {presentation.map.lanes.map(lane => (
            <HudMetric
              key={lane.zoneKey}
              label={lane.zoneKey === 'agent' ? 'Agent 占用' : 'Standard 占用'}
              value={`${lane.utilizationPercent}%`}
              detail={`${lane.runningCount}/${lane.capacity || '—'}`}
              token={lane.colorToken}
            />
          ))}
          <button type="button" className="command-center-refresh" onClick={reload} disabled={runtimeLoading}>
            {runtimeLoading ? '刷新中' : '刷新 Runtime'}
          </button>
        </header>

        {runtimeError && (
          <div className="command-center-runtime-error" role="alert">
            <strong>Runtime 快照暂不可用</strong>
            <span>{runtimeError}。地图保留最后一次成功快照。</span>
          </div>
        )}

        <CommandCenterCanvas
          map={presentation.map}
          visibleLimit={visibleLimit}
          onOpenReview={openReview}
          onOpenOverflow={setOverflowLane}
        />
      </section>

      <Modal
        title={overflowLane ? `${overflowLane.title} · 全部运行 Review` : '运行 Review'}
        open={Boolean(overflowLane)}
        footer={null}
        width={720}
        onCancel={() => setOverflowLane(null)}
        destroyOnHidden
      >
        {overflowLane?.runningItemsTruncated && (
          <p className="command-center-modal-notice">当前列表为 Runtime 快照的有界结果。</p>
        )}
        <div className="command-center-modal-list">
          {(overflowLane?.runningItems || []).map(item => (
            <button
              type="button"
              key={`${item.jobId}:${item.taskId}:${item.reviewKey}`}
              onClick={() => openReview(item)}
            >
              <span className={`command-center-modal-token is-${item.engineToken}`} aria-hidden="true" />
              <span>
                <strong>{item.projectName}</strong>
                <small>{item.displayName} · {item.providerModelLabel}</small>
              </span>
              <em>{item.stageLabel}</em>
            </button>
          ))}
        </div>
      </Modal>
    </main>
  );
}


function HudMetric({ label, value, detail, token = 'neutral' }) {
  return (
    <div className={`command-center-hud-metric is-${token}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}


function useRunningItemLimit() {
  const [limit, setLimit] = useState(readRunningItemLimit);
  useEffect(() => {
    const update = () => setLimit(readRunningItemLimit());
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);
  return limit;
}


function readRunningItemLimit() {
  if (typeof window === 'undefined') return 6;
  if (window.innerWidth <= 700) return 2;
  if (window.innerWidth <= 1100) return 4;
  return 6;
}


function freshnessLabel(value) {
  return {
    FRESH: 'Runtime 实时',
    STALE: 'Runtime 已过期',
    LOADING: 'Runtime 连接中',
    EMPTY: 'Runtime 暂无数据'
  }[value] || 'Runtime 状态未知';
}


function formatSnapshotTime(value) {
  if (!value) return '等待首轮快照';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '快照时间未知';
  return `更新于 ${new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(date)}`;
}
