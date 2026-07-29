export const agentBudgetKeys = [
  'maxTurns',
  'maxToolCalls',
  'maxSourceBytes',
  'timeoutSeconds',
  'inlineDiffBytes',
  'maxEvidenceCalls',
  'convergeAtCalls',
  'submitByTurn'
];

export const defaultAgentBudgets = {
  maxTurns: 12,
  maxToolCalls: 40,
  maxSourceBytes: 200000,
  timeoutSeconds: 600,
  inlineDiffBytes: 200000,
  maxEvidenceCalls: 10,
  convergeAtCalls: 8,
  submitByTurn: 9
};

export const defaultAgentBudgetLimits = {
  maxTurns: { min: 6, max: 18 },
  maxToolCalls: { min: 10, max: 60 },
  maxSourceBytes: { min: 10000, max: 300000 },
  timeoutSeconds: { min: 60, max: 900 },
  inlineDiffBytes: { min: 10000, max: 300000 },
  maxEvidenceCalls: { min: 4, max: 15 },
  convergeAtCalls: { min: 2, max: 13 },
  submitByTurn: { min: 3, max: 15 }
};

export function normalizeAgentBudgets(settings) {
  const source = settings?.budgets && typeof settings.budgets === 'object'
    ? settings.budgets
    : settings?.budgetDefaults;
  return Object.fromEntries(agentBudgetKeys.map(key => {
    const value = Number(source?.[key]);
    return [key, Number.isInteger(value) ? value : defaultAgentBudgets[key]];
  }));
}

export function agentBudgetLimits(settings) {
  return Object.fromEntries(agentBudgetKeys.map(key => {
    const source = settings?.budgetLimits?.[key];
    const minimum = Number(source?.min);
    const maximum = Number(source?.max);
    return [
      key,
      {
        min: Number.isInteger(minimum) ? minimum : defaultAgentBudgetLimits[key].min,
        max: Number.isInteger(maximum) ? maximum : defaultAgentBudgetLimits[key].max
      }
    ];
  }));
}

export function validateAgentBudgets(budgets, settings) {
  const limits = agentBudgetLimits(settings);
  for (const key of agentBudgetKeys) {
    const value = Number(budgets?.[key]);
    if (!Number.isInteger(value)) return `${key} 必须是整数`;
    if (value < limits[key].min || value > limits[key].max) {
      return `${key} 必须在 ${limits[key].min}～${limits[key].max} 之间`;
    }
  }
  if (budgets.convergeAtCalls > budgets.maxEvidenceCalls - 2) {
    return '收敛起点必须至少比证据调用上限小 2';
  }
  if (budgets.submitByTurn > budgets.maxTurns - 3) {
    return '提交回合必须至少为最终提交保留 3 个回合';
  }
  if (budgets.maxToolCalls < budgets.maxEvidenceCalls + 1) {
    return '工具调用上限必须至少比证据调用上限多 1';
  }
  return null;
}

export function hasRaisedAgentBudget(budgets, settings) {
  const defaults = settings?.budgetDefaults || defaultAgentBudgets;
  return agentBudgetKeys.some(key => Number(budgets?.[key]) > Number(defaults[key]));
}

export function bytesToKilobytes(value) {
  const bytes = Number(value);
  return Number.isFinite(bytes) ? bytes / 1000 : undefined;
}

export function kilobytesToBytes(value) {
  const kilobytes = Number(value);
  return Number.isFinite(kilobytes) ? Math.round(kilobytes * 1000) : undefined;
}

export function formatAgentBudgetSummary(budgets) {
  if (!budgets || typeof budgets !== 'object') return '';
  const required = agentBudgetKeys.every(key => Number.isInteger(Number(budgets[key])));
  if (!required) return '';
  return [
    `${budgets.maxTurns} turns`,
    `${budgets.maxToolCalls} tools`,
    `${Math.round(budgets.maxSourceBytes / 1000)} KB source`,
    `${budgets.timeoutSeconds} 秒`,
    `${budgets.maxEvidenceCalls} evidence`,
    `第 ${budgets.convergeAtCalls} 次收敛`,
    `第 ${budgets.submitByTurn} 回合提交`
  ].join(' / ');
}
