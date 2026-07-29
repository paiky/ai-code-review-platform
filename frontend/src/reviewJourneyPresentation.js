export const AGENT_REVIEW_ANIMATION_STYLES = Object.freeze(['BRAIN']);

const AGENT_PHASE_TO_HERO_STATE = Object.freeze({
  AGENT_ANALYZING: 'ANALYZING',
  AGENT_TOOL_ACTIVITY: 'EVIDENCE',
  AGENT_CONVERGING: 'CONVERGING',
  AGENT_SUBMITTING: 'SUBMITTING'
});

const HERO_COPY = Object.freeze({
  QUEUED: {
    title: 'Review 正在等待调度',
    description: '任务已进入队列，页面会继续使用现有轮询更新真实状态。'
  },
  ANALYZING: {
    title: '正在分析本次代码变更',
    description: '平台正在准备或分析本次变更，只展示可验证的执行状态。'
  },
  EVIDENCE: {
    title: '正在进行受控只读取证',
    description: 'Agent 只围绕已有风险假设补充白名单范围内的证据。'
  },
  CONVERGING: {
    title: '正在收敛 Review 结论',
    description: '取证范围已经收拢，当前正在整理结构化结论。'
  },
  SUBMITTING: {
    title: '正在提交 Review Card',
    description: '结构化结果正在提交和保存，页面会等待后端终态。'
  },
  SUCCESS: {
    title: 'Review 已完成',
    description: '正式结果已保存，可继续查看阶段详情和质量问题。'
  },
  FALLBACK: {
    title: 'Agent 已转交 Standard Review',
    description: 'Agent 未形成有效终态，任务已按既有策略由 Standard Review 接管。'
  },
  FAILED: {
    title: 'Review 执行失败',
    description: '本次 Review 没有成功完成，可查看固定原因摘要和建议动作。'
  },
  CANCELLED: {
    title: 'Review 已取消',
    description: '本次执行已停止，不会把取消状态显示为成功或失败。'
  },
  SKIPPED: {
    title: 'Review 已跳过',
    description: '本次没有执行 Review；历史记录不足时不会补造原因。'
  },
  HISTORY: {
    title: '历史任务未记录完整进度',
    description: '仅展示现有可靠记录，不补造阶段、时间、耗时或执行状态。'
  }
});

export function buildReviewHeroModel(journey) {
  const source = journey && typeof journey === 'object' ? journey : {};
  const state = reviewHeroState(source);
  const copy = HERO_COPY[state] || HERO_COPY.HISTORY;
  const kind = source.historical
    ? 'HISTORICAL'
    : source.engineKind === 'STANDARD'
      ? 'PROVIDER'
      : 'BRAIN';
  const identity = source.engineLabel || '历史任务未记录';
  const provider = source.providerModelLabel || 'Provider/model 未记录';
  return {
    kind,
    style: kind === 'BRAIN' ? 'BRAIN' : null,
    state,
    title: copy.title,
    description: copy.description,
    identity,
    provider,
    ariaLabel: `${identity}：${copy.title}`,
    animated: shouldAnimateReview({
      state,
      reducedMotion: false
    })
  };
}

export function reviewTimelineMode(journey) {
  return journey?.running ? 'FULL' : 'COMPACT';
}

export function visibleReviewJourneyStages(journey) {
  return (Array.isArray(journey?.stages) ? journey.stages : [])
    .filter(stage => stage?.visible);
}

export function resolveOpenReviewJourneyStage(journey, stageId) {
  if (!stageId) return null;
  return visibleReviewJourneyStages(journey)
    .find(stage => stage.id === stageId) || null;
}

export function buildStageAlertModel(stage) {
  if (!stage || !['WARNING', 'FAILED'].includes(stage.status)) return null;
  return {
    status: stage.status,
    title: stage.status === 'FAILED' ? '阶段执行失败' : '阶段存在警告',
    reason: stage.warningSummary || (
      stage.status === 'FAILED'
        ? '该阶段没有成功完成。'
        : '该阶段存在不影响主状态的安全警告。'
    ),
    action: stage.suggestedAction || (
      stage.status === 'FAILED'
        ? '查看阶段详情，并按页面现有操作决定是否重试。'
        : '继续以最终 Review 状态和正式结果为准。'
    )
  };
}

export function isReviewStageActivationKey(key) {
  return key === 'Enter' || key === ' ' || key === 'Spacebar';
}

export function isReviewJourneyDismissKey(key) {
  return key === 'Escape';
}

export function reviewTimelineOrientation(viewportWidth) {
  const width = Number(viewportWidth);
  return Number.isFinite(width) && width <= 600 ? 'VERTICAL' : 'HORIZONTAL';
}

export function shouldAnimateReview({ state, reducedMotion }) {
  if (reducedMotion) return false;
  return [
    'QUEUED',
    'ANALYZING',
    'EVIDENCE',
    'CONVERGING',
    'SUBMITTING',
    'FALLBACK'
  ].includes(state);
}

function reviewHeroState(journey) {
  if (journey.historical || journey.status === 'UNKNOWN') return 'HISTORY';
  if (journey.engineKind === 'FALLBACK') return 'FALLBACK';
  if (journey.status === 'QUEUED') return 'QUEUED';
  if (journey.status === 'SUCCESS') return 'SUCCESS';
  if (journey.status === 'FAILED') return 'FAILED';
  if (journey.status === 'CANCELLED') return 'CANCELLED';
  if (journey.status === 'SKIPPED') return 'SKIPPED';
  const agentPhase = journey.agentSummary?.phase;
  if (AGENT_PHASE_TO_HERO_STATE[agentPhase]) {
    return AGENT_PHASE_TO_HERO_STATE[agentPhase];
  }
  return journey.status === 'RUNNING' ? 'ANALYZING' : 'HISTORY';
}
