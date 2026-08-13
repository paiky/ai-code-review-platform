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

export const recommendedAgentBudgetValues = Object.freeze({
  maxTurns: [6, 9, 12, 14, 16, 18],
  maxToolCalls: [10, 20, 30, 40, 50, 60],
  maxSourceBytes: [10_000, 50_000, 100_000, 200_000, 300_000],
  timeoutSeconds: [60, 180, 300, 600, 900],
  inlineDiffBytes: [10_000, 50_000, 100_000, 200_000, 300_000],
  maxEvidenceCalls: [4, 6, 8, 10, 12, 15],
  convergeAtCalls: [2, 4, 6, 8, 10, 13],
  submitByTurn: [3, 6, 9, 12, 15]
});

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

export function buildAgentBudgetOptions(fieldKey, budgets, settings) {
  if (!agentBudgetKeys.includes(fieldKey)) return [];
  const limits = agentBudgetLimits(settings)[fieldKey];
  const serverDefault = Number(settings?.budgetDefaults?.[fieldKey]);
  const defaultValue = Number.isInteger(serverDefault)
    ? serverDefault
    : defaultAgentBudgets[fieldKey];
  const currentValue = Number(budgets?.[fieldKey]);
  const recommendedValues = recommendedAgentBudgetValues[fieldKey] || [];
  const recommendedSet = new Set(recommendedValues);
  const values = new Set([...recommendedValues, defaultValue]);
  if (Number.isInteger(currentValue)) values.add(currentValue);

  return [...values]
    .filter(value => Number.isInteger(value) && value >= limits.min && value <= limits.max)
    .sort((left, right) => left - right)
    .map(value => {
      const nextBudgets = { ...budgets, [fieldKey]: value };
      const disabledReason = value === currentValue
        ? null
        : validateAgentBudgets(nextBudgets, settings);
      return {
        value,
        isDefault: value === defaultValue,
        isCurrentCustom: value === currentValue
          && value !== defaultValue
          && !recommendedSet.has(value),
        disabled: Boolean(disabledReason),
        disabledReason
      };
    });
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
