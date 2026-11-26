[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $InputPath,
    [Parameter(Mandatory = $true)] [string] $OutputDirectory
)

$ErrorActionPreference = 'Stop'

function Get-NonnegativeInteger($Value, [string] $Field) {
    if ($null -eq $Value) { return $null }
    if (($Value -isnot [int] -and $Value -isnot [long]) -or $Value -lt 0) {
        throw "Expected a nonnegative integer for $Field."
    }
    return [long] $Value
}

function Get-PositiveInteger($Value, [string] $Field) {
    $number = Get-NonnegativeInteger $Value $Field
    if ($null -eq $number -or $number -eq 0) { throw "Expected a positive integer for $Field." }
    return $number
}

function Get-AllowedValue($Value, [string[]] $Allowed) {
    if ($Value -is [string] -and $Value -cin $Allowed) { return $Value }
    return $null
}

function Copy-Counts($Record, $Target, [string[]] $Fields) {
    foreach ($field in $Fields) { $Target[$field] = Get-NonnegativeInteger $Record.$field $field }
}

function Copy-Booleans($Record, $Target, [string[]] $Fields) {
    foreach ($field in $Fields) {
        $Target[$field] = if ($Record.$field -is [bool]) { $Record.$field } else { $null }
    }
}

function Get-Pagination($Run) {
    $counts = [ordered] @{
        callCount = $null
        nonEmptySuccessCount = $null
        emptySuccessCount = $null
        returnedLines = $null
        contentUnavailableCount = $null
        outOfBoundsCount = $null
        unknownReasonCount = $null
        otherFailureCount = $null
        unknownOutcomeCount = $null
    }
    $fields = @($counts.Keys)
    $source = 'UNAVAILABLE'
    if ($null -ne $Run.pagination -and $null -ne $Run.toolEvents) {
        throw 'Provide either pagination or toolEvents for an Agent Run.'
    }

    if ($null -ne $Run.pagination) {
        Copy-Counts $Run.pagination $counts $fields
        $source = 'RECORDED_SUMMARY'
        $observedClasses = @('nonEmptySuccessCount', 'emptySuccessCount', 'contentUnavailableCount', 'outOfBoundsCount', 'otherFailureCount')
        $classified = ($observedClasses | ForEach-Object { $counts[$_] } | Measure-Object -Sum).Sum
        if ($null -ne $counts.callCount -and $classified -gt $counts.callCount) {
            throw 'Pagination classifications exceed the provided callCount.'
        }
    }
    elseif ($null -ne $Run.toolEvents) {
        if ($Run.toolEvents -isnot [array] -or $Run.toolEvents.Count -gt 5000) {
            throw 'Expected a toolEvents array with at most 5000 entries per Run.'
        }
        $source = 'TOOL_EVENTS'
        foreach ($field in $fields) { $counts[$field] = 0L }
        $eventsByKey = @{}
        foreach ($event in $Run.toolEvents) {
            if ($event.tool -notin @('read_diff_range', 'READ_DIFF_RANGE')) { continue }
            $claim = Get-PositiveInteger $event.claimAttempt 'claimAttempt'
            $sequence = Get-PositiveInteger $event.sequence 'sequence'
            $key = "$claim/$sequence"
            $lines = Get-NonnegativeInteger $event.returnedLines 'returnedLines'
            $classification = $null
            $outcomeUnknown = $false
            $reasonUnknown = $false

            if ($event.status -in @('SUCCESS', 'SUCCEEDED') -and $null -ne $lines) {
                $classification = if ($lines -gt 0) { 'nonEmptySuccessCount' } else { 'emptySuccessCount' }
                $reasonUnknown = $lines -eq 0 -and $event.errorCode -cnotmatch '^[A-Z_]{1,64}$'
            }
            elseif ($event.status -in @('FAILED', 'ERROR')) {
                $lines = 0L
                $classification = switch -CaseSensitive ($event.errorCode) {
                    'DIFF_CONTENT_UNAVAILABLE' { 'contentUnavailableCount'; break }
                    'DIFF_RANGE_OUT_OF_BOUNDS' { 'outOfBoundsCount'; break }
                    { $_ -is [string] -and $_ -cmatch '^[A-Z_]{1,64}$' } { 'otherFailureCount'; break }
                    default { $null }
                }
                $reasonUnknown = $null -eq $classification
            }
            else {
                $lines = $null
                $outcomeUnknown = $true
                $reasonUnknown = $true
            }
            $signature = "$classification/$lines/$outcomeUnknown/$reasonUnknown"
            if ($eventsByKey.ContainsKey($key)) {
                if ($eventsByKey[$key] -ne $signature) { throw 'Conflicting duplicate pagination tool event.' }
                continue
            }

            $eventsByKey[$key] = $signature
            $counts.callCount++
            if ($classification) { $counts[$classification]++ }
            if ($reasonUnknown) { $counts.unknownReasonCount++ }
            if ($outcomeUnknown) { $counts.unknownOutcomeCount++ }
            if ($null -eq $lines) { $counts.returnedLines = $null }
            elseif ($null -ne $counts.returnedLines) { $counts.returnedLines += $lines }
        }
    }

    $state = 'UNKNOWN'
    if ($counts.callCount -eq 0) { $state = 'NO_CALLS' }
    elseif ($counts.callCount -gt 0) { $state = 'CALLS_RECORDED' }
    elseif (@($fields | Where-Object { $null -ne $counts[$_] }).Count -gt 0) { $state = 'PARTIAL_COUNTS' }
    $counts['source'] = $source
    $counts['state'] = $state
    return [pscustomobject] $counts
}

function Measure-KnownValues($Records, [string] $Field) {
    $known = @($Records | Where-Object { $null -ne $_.$Field })
    $summary = [ordered] @{ knownCount = $known.Count; unknownCount = $Records.Count - $known.Count }
    if ($known.Count -gt 0) {
        $measurement = $known | Measure-Object -Property $Field -Sum -Minimum -Maximum
        $summary['sum'] = $measurement.Sum
        $summary['min'] = $measurement.Minimum
        $summary['max'] = $measurement.Maximum
    }
    return $summary
}

function Measure-EmptyReadRate($Records) {
    $measurable = @($Records | Where-Object {
        $null -ne $_.pagination.nonEmptySuccessCount -and $null -ne $_.pagination.emptySuccessCount -and
            -not ($_.pagination.unknownOutcomeCount -gt 0)
    })
    $successfulCalls = ($measurable | ForEach-Object {
        $_.pagination.nonEmptySuccessCount + $_.pagination.emptySuccessCount
    } | Measure-Object -Sum).Sum
    $empty = ($measurable | ForEach-Object { $_.pagination.emptySuccessCount } | Measure-Object -Sum).Sum
    $knownEmptyOutsideRate = ($Records | Where-Object {
        $null -ne $_.pagination.emptySuccessCount -and
            ($null -eq $_.pagination.nonEmptySuccessCount -or $_.pagination.unknownOutcomeCount -gt 0)
    } | ForEach-Object { $_.pagination.emptySuccessCount } | Measure-Object -Sum).Sum
    return [ordered] @{
        knownRunCount = $measurable.Count
        unknownRunCount = $Records.Count - $measurable.Count
        successfulCallCount = [long] $successfulCalls
        emptySuccessCount = [long] $empty
        knownEmptySuccessCountOutsideRate = [long] $knownEmptyOutsideRate
        rate = if ($successfulCalls -gt 0) { [math]::Round($empty / $successfulCalls, 4) } else { $null }
    }
}

function Format-Cell($Value) {
    if ($null -eq $Value) { return '未知' }
    if ($Value -is [bool]) { if ($Value) { return '是' } else { return '否' } }
    return [string] $Value
}

$sourceFile = Get-Item -LiteralPath $InputPath
if ($sourceFile.PSIsContainer -or $sourceFile.Length -gt 8MB) { throw 'Expected a JSON file of at most 8 MiB.' }
$source = Get-Content -Raw -Encoding UTF8 -LiteralPath $sourceFile.FullName | ConvertFrom-Json
if ((Get-NonnegativeInteger $source.schemaVersion 'schemaVersion') -ne 1) { throw 'Unsupported input schemaVersion.' }
$sourceKind = Get-AllowedValue $source.sourceKind @('DOCUMENTED_HISTORICAL_SAMPLES', 'SANITIZED_LOCAL_EXPORT', 'SYNTHETIC_FIXTURE')
if (-not $sourceKind) { throw 'Unsupported sourceKind.' }
foreach ($listName in @('agentRuns', 'agentReplays', 'standardRuns', 'findingReviewSamples', 'historicalSignals')) {
    if ($null -ne $source.$listName -and ($source.$listName -isnot [array] -or $source.$listName.Count -gt 500)) {
        throw "Expected $listName to be an array with at most 500 entries."
    }
}

$roles = @('BASELINE', 'CANDIDATE', 'HISTORICAL')
$agentRunKeys = @{}
$agentRuns = @(foreach ($record in $source.agentRuns) {
    $row = [ordered] @{
        taskId = Get-PositiveInteger $record.taskId 'taskId'
        runId = Get-PositiveInteger $record.runId 'runId'
        triggerType = Get-AllowedValue $record.triggerType @('MR', 'PUSH')
        comparisonRole = Get-AllowedValue $record.comparisonRole $roles
        diffMode = Get-AllowedValue $record.diffMode @('INLINE', 'TOOL_PAGED')
        status = Get-AllowedValue $record.status @('PENDING', 'RUNNING', 'SUCCESS', 'SUCCEEDED', 'FAILED', 'CANCELED', 'CANCELLED', 'TIMED_OUT', 'SKIPPED')
        effectiveEngine = Get-AllowedValue $record.effectiveEngine @('AGENT', 'STANDARD', 'STANDARD_FALLBACK')
        pagination = Get-Pagination $record
    }
    if (-not $row.triggerType) { throw 'Agent Runs require an MR or PUSH triggerType.' }
    $runKey = "$($row.taskId)/$($row.runId)"
    if ($agentRunKeys.ContainsKey($runKey)) { throw 'Duplicate Agent taskId/runId.' }
    $agentRunKeys[$runKey] = $true
    Copy-Counts $record $row @('changedFileCount', 'queuedDiffBytes', 'firstRequestBytes', 'firstRequestKbApprox', 'durationMs', 'formalRunId', 'findingCount', 'maxNoNewEvidenceTurns')
    Copy-Booleans $record $row @('recoveredAfterDiffFailure')
    [pscustomobject] $row
})
$agentRuns = @($agentRuns | Sort-Object taskId, runId)

$agentReplays = @(foreach ($record in $source.agentReplays) {
    $row = [ordered] @{
        taskId = Get-PositiveInteger $record.taskId 'taskId'
        triggerType = Get-AllowedValue $record.triggerType @('MR', 'PUSH')
    }
    if (-not $row.triggerType) { throw 'Agent replay records require an MR or PUSH triggerType.' }
    Copy-Counts $record $row @('beforeReadablePatchCount', 'supplementedPatchCount', 'afterReadablePatchCount', 'readablePatchTargetCount')
    Copy-Booleans $record $row @('verifiedPagedRead')
    [pscustomobject] $row
})
$agentReplays = @($agentReplays | Sort-Object taskId, triggerType)

$standardKeys = @{}
$standardRuns = @(foreach ($record in $source.standardRuns) {
    $row = [ordered] @{
        taskId = Get-PositiveInteger $record.taskId 'taskId'
        comparisonRole = Get-AllowedValue $record.comparisonRole $roles
    }
    $standardKey = "$($row.taskId)/$($row.comparisonRole)"
    if ($standardKeys.ContainsKey($standardKey)) { throw 'Duplicate Standard taskId/comparisonRole.' }
    $standardKeys[$standardKey] = $true
    Copy-Counts $record $row @('queryCount', 'matchedFileCount', 'candidateSnippetCount', 'includedSnippetCount', 'contextPromptChars', 'targetContextChars', 'plannerSignalCount')
    Copy-Booleans $record $row @('hasDeletionNeighborEvidence', 'hasImplementationEvidence')
    $row['overTarget'] = if ($null -ne $row.contextPromptChars -and $null -ne $row.targetContextChars) {
        $row.contextPromptChars -gt $row.targetContextChars
    } else { $null }
    $row['zeroMatchesAfterSearch'] = if ($row.queryCount -gt 0 -and $null -ne $row.matchedFileCount) {
        $row.matchedFileCount -eq 0
    } else { $null }
    $row['zeroSnippetsAfterSearch'] = if ($row.queryCount -gt 0 -and $null -ne $row.includedSnippetCount) {
        $row.includedSnippetCount -eq 0
    } else { $null }
    $row['zeroSnippetsWithCandidates'] = if ($null -ne $row.candidateSnippetCount -and $null -ne $row.includedSnippetCount) {
        $row.candidateSnippetCount -gt 0 -and $row.includedSnippetCount -eq 0
    } else { $null }
    [pscustomobject] $row
})
$standardRuns = @($standardRuns | Sort-Object taskId, comparisonRole)

$historicalSignals = @(foreach ($record in $source.historicalSignals) {
    if ($record.scope -isnot [string] -or $record.scope -cnotmatch '^[A-Z0-9_]{1,64}$') {
        throw 'Expected a safe identifier for historicalSignals.scope.'
    }
    $row = [ordered] @{ scope = $record.scope }
    Copy-Counts $record $row @('taskCount', 'runCount', 'firstRequestFailureCount', 'affectedTaskCount', 'knownHttpStatusCount', 'recoveredTaskCount', 'summaryTurnZeroCount', 'summaryUsageMissingCount', 'turnEventsCoveredRunCount')
    [pscustomobject] $row
})
$historicalSignals = @($historicalSignals | Sort-Object scope)

$agentGroups = @(foreach ($trigger in @('MR', 'PUSH')) {
    $runs = @($agentRuns | Where-Object triggerType -eq $trigger)
    $replays = @($agentReplays | Where-Object triggerType -eq $trigger)
    $pagination = @($runs | ForEach-Object { $_.pagination })
    [ordered] @{
        triggerType = $trigger
        runCount = $runs.Count
        taskCount = @($runs | Select-Object -ExpandProperty taskId -Unique).Count
        replayCount = $replays.Count
        replayPatchCounts = [ordered] @{
            before = Measure-KnownValues $replays 'beforeReadablePatchCount'
            supplemented = Measure-KnownValues $replays 'supplementedPatchCount'
            after = Measure-KnownValues $replays 'afterReadablePatchCount'
            target = Measure-KnownValues $replays 'readablePatchTargetCount'
        }
        paginationCoverage = [ordered] @{
            observedCallsRunCount = @($pagination | Where-Object state -eq 'CALLS_RECORDED').Count
            noCallsRunCount = @($pagination | Where-Object state -eq 'NO_CALLS').Count
            partialCountsRunCount = @($pagination | Where-Object state -eq 'PARTIAL_COUNTS').Count
            unknownRunCount = @($pagination | Where-Object state -eq 'UNKNOWN').Count
        }
        paginationMetrics = [ordered] @{
            nonEmptySuccessCount = Measure-KnownValues $pagination 'nonEmptySuccessCount'
            returnedLines = Measure-KnownValues $pagination 'returnedLines'
            contentUnavailableCount = Measure-KnownValues $pagination 'contentUnavailableCount'
            outOfBoundsCount = Measure-KnownValues $pagination 'outOfBoundsCount'
            unknownReasonCount = Measure-KnownValues $pagination 'unknownReasonCount'
            unknownOutcomeCount = Measure-KnownValues $pagination 'unknownOutcomeCount'
        }
        emptySuccessRate = Measure-EmptyReadRate $runs
        recoveredRunCount = @($runs | Where-Object { $_.recoveredAfterDiffFailure -eq $true }).Count
        recoveryObservedRunCount = @($runs | Where-Object { $null -ne $_.recoveredAfterDiffFailure }).Count
        queuedDiffBytes = Measure-KnownValues $runs 'queuedDiffBytes'
        firstRequestBytes = Measure-KnownValues $runs 'firstRequestBytes'
        firstRequestKbApprox = Measure-KnownValues $runs 'firstRequestKbApprox'
        durationMs = Measure-KnownValues $runs 'durationMs'
        findingCount = Measure-KnownValues $runs 'findingCount'
    }
})

$standardSummary = [ordered] @{
    recordCount = $standardRuns.Count
    taskCount = @($standardRuns | Select-Object -ExpandProperty taskId -Unique).Count
    searchCount = Measure-KnownValues $standardRuns 'queryCount'
    matchedFileCount = Measure-KnownValues $standardRuns 'matchedFileCount'
    includedSnippetCount = Measure-KnownValues $standardRuns 'includedSnippetCount'
    overTargetCount = @($standardRuns | Where-Object { $_.overTarget -eq $true }).Count
    targetMeasuredCount = @($standardRuns | Where-Object { $null -ne $_.overTarget }).Count
    zeroSnippetsAfterSearchCount = @($standardRuns | Where-Object { $_.zeroSnippetsAfterSearch -eq $true }).Count
    searchedWithInclusionMeasuredCount = @($standardRuns | Where-Object { $null -ne $_.zeroSnippetsAfterSearch }).Count
    zeroSnippetsWithCandidatesCount = @($standardRuns | Where-Object { $_.zeroSnippetsWithCandidates -eq $true }).Count
    candidateAndInclusionMeasuredCount = @($standardRuns | Where-Object { $null -ne $_.candidateSnippetCount -and $null -ne $_.includedSnippetCount }).Count
}
$findingReviewCandidates = @(foreach ($task in ($agentRuns | Group-Object taskId, triggerType)) {
    $baseline = @($task.Group | Where-Object comparisonRole -eq 'BASELINE')
    $candidate = @($task.Group | Where-Object comparisonRole -eq 'CANDIDATE')
    if ($baseline.Count -eq 1 -and $candidate.Count -eq 1 -and $baseline[0].findingCount -gt 0 -and $candidate[0].findingCount -eq 0) {
        [ordered] @{
            taskId = $candidate[0].taskId
            baselineRunId = $baseline[0].runId
            candidateRunId = $candidate[0].runId
            baselineFindingCount = $baseline[0].findingCount
            candidateFindingCount = $candidate[0].findingCount
            reason = 'FINDING_COUNT_FELL_TO_ZERO'
        }
    }
})
$findingSampleKeys = @{}
$findingSamples = @(foreach ($record in $source.findingReviewSamples) {
    $row = [ordered] @{
        taskId = Get-PositiveInteger $record.taskId 'taskId'
        runId = if ($null -ne $record.runId) { Get-PositiveInteger $record.runId 'runId' } else { $null }
        findingIndex = Get-NonnegativeInteger $record.findingIndex 'findingIndex'
        severity = Get-AllowedValue $record.severity @('MINOR', 'MAJOR', 'CRITICAL', 'HIGH')
        contextStatus = Get-AllowedValue $record.contextStatus @('SUFFICIENT', 'PARTIAL', 'INSUFFICIENT')
        confidence = Get-AllowedValue $record.confidence @('LOW', 'MEDIUM', 'HIGH')
    }
    if ($null -eq $row.findingIndex) { throw 'Expected findingIndex in findingReviewSamples.' }
    if ($row.severity -eq 'HIGH') { $row.severity = 'MAJOR' }
    $key = "$($row.taskId)/$($row.runId)/$($row.findingIndex)"
    if ($findingSampleKeys.ContainsKey($key)) { throw 'Duplicate Finding taskId/runId/findingIndex.' }
    $findingSampleKeys[$key] = $true
    [pscustomobject] $row
})
$measurableFindings = @($findingSamples | Where-Object { $_.severity -and $_.contextStatus -and $_.confidence })
$highRiskFindingCandidates = @($measurableFindings | Where-Object {
    $_.severity -in @('MAJOR', 'CRITICAL') -and $_.contextStatus -eq 'PARTIAL' -and $_.confidence -eq 'HIGH'
} | Sort-Object taskId, runId, findingIndex)
$findingSampleCoverage = [ordered] @{
    sampleCount = $findingSamples.Count
    measurableCount = $measurableFindings.Count
    unknownCount = $findingSamples.Count - $measurableFindings.Count
    candidateCount = $highRiskFindingCandidates.Count
}
$report = [ordered] @{
    schemaVersion = 1
    sourceKind = $sourceKind
    agentGroups = $agentGroups
    agentRuns = $agentRuns
    agentReplays = $agentReplays
    standardSummary = $standardSummary
    standardRuns = $standardRuns
    findingReviewCandidates = $findingReviewCandidates
    findingSampleCoverage = $findingSampleCoverage
    highRiskFindingCandidates = $highRiskFindingCandidates
    historicalSignals = $historicalSignals
}

$markdown = @(
    '# 审查质量监测 · M0 离线报告'
    ''
    ('数据来源 `{0}`。观察范围仅限输入样本。' -f $sourceKind)
    '「未知」表示输入未提供可核对的字段。回放验证、运行记录和历史统计使用各自的样本分母。'
    ''
    '## Agent 监测汇总'
    ''
    '| 触发 | 任务 / Run | 分页有调用 / 无调用 / 部分 / 未知 | 可核对分母的空读 / 成功调用 | 未计入比率的已知空读 | 恢复 / 可核对 |'
    '| --- | --- | --- | --- | --- | --- |'
    foreach ($group in $agentGroups) {
        $coverage = $group.paginationCoverage
        $empty = $group.emptySuccessRate
        '| {0} | {1} / {2} | {3} / {4} / {5} / {6} | {7} / {8} | {9} | {10} / {11} |' -f $group.triggerType, $group.taskCount, $group.runCount, $coverage.observedCallsRunCount, $coverage.noCallsRunCount, $coverage.partialCountsRunCount, $coverage.unknownRunCount, $empty.emptySuccessCount, $empty.successfulCallCount, $empty.knownEmptySuccessCountOutsideRate, $group.recoveredRunCount, $group.recoveryObservedRunCount
    }
    '部分历史记录只有已发生的空读数或调用结果未知。这些已知空读单列，分母完整的记录进入比率。'
    ''
    '## Agent 补取回放'
    ''
    '| 任务 | 触发 | 原有 patch | 补齐 patch | 补取后 patch | 目标 patch | 分页验证 |'
    '| --- | --- | --- | --- | --- | --- | --- |'
    foreach ($row in ($agentReplays | Select-Object -First 30)) {
        '| #{0} | {1} | {2} | {3} | {4} | {5} | {6} |' -f $row.taskId, $row.triggerType, (Format-Cell $row.beforeReadablePatchCount), (Format-Cell $row.supplementedPatchCount), (Format-Cell $row.afterReadablePatchCount), (Format-Cell $row.readablePatchTargetCount), (Format-Cell $row.verifiedPagedRead)
    }
    ''
    '## Agent 分页与终态'
    ''
    '| 任务 / Run | 对照 | 入队 Diff 字节 / 模式 | 首轮请求 | 分页次数 / 有内容 / 返回行数 | 空读 / 缺失 / 越界 / 原因未知 | 恢复 / 最长无新证据轮数 | 总耗时（ms） | 状态 / 正式 Run / Finding |'
    '| --- | --- | --- | --- | --- | --- | --- | --- | --- |'
    foreach ($row in ($agentRuns | Select-Object -First 30)) {
        $page = $row.pagination
        $firstRequest = if ($null -ne $row.firstRequestBytes) { "$($row.firstRequestBytes) B" }
        elseif ($null -ne $row.firstRequestKbApprox) { "约 $($row.firstRequestKbApprox) KB" }
        else { '未知' }
        '| #{0} / #{1} | {2} | {3} / {4} | {5} | {6} / {7} / {8} | {9} / {10} / {11} / {12} | {13} / {14} | {15} | {16} / {17} / {18} |' -f $row.taskId, $row.runId, (Format-Cell $row.comparisonRole), (Format-Cell $row.queuedDiffBytes), (Format-Cell $row.diffMode), $firstRequest, (Format-Cell $page.callCount), (Format-Cell $page.nonEmptySuccessCount), (Format-Cell $page.returnedLines), (Format-Cell $page.emptySuccessCount), (Format-Cell $page.contentUnavailableCount), (Format-Cell $page.outOfBoundsCount), (Format-Cell $page.unknownReasonCount), (Format-Cell $row.recoveredAfterDiffFailure), (Format-Cell $row.maxNoNewEvidenceTurns), (Format-Cell $row.durationMs), (Format-Cell $row.status), (Format-Cell $row.formalRunId), (Format-Cell $row.findingCount)
    }
    ''
    '## Standard 检索与上下文'
    ''
    ('Context Pack 超出裁剪目标 {0} 条，可核对 {1} 条，共 {2} 条记录。' -f $standardSummary.overTargetCount, $standardSummary.targetMeasuredCount, $standardSummary.recordCount)
    ('已搜索但保留 0 条引用片段 {0} 条，已搜索且保留数可核对 {1} 条。候选缺失时，建议回放确定证据在哪一步丢失。' -f $standardSummary.zeroSnippetsAfterSearchCount, $standardSummary.searchedWithInclusionMeasuredCount)
    ''
    '| 任务 | 对照 | 信号 / 查询 / 命中文件 | 候选 / 保留片段 | 实际 / 目标字符 | 删除附近 / 实现证据 |'
    '| --- | --- | --- | --- | --- | --- |'
    foreach ($row in ($standardRuns | Select-Object -First 30)) {
        '| #{0} | {1} | {2} / {3} / {4} | {5} / {6} | {7} / {8} | {9} / {10} |' -f $row.taskId, (Format-Cell $row.comparisonRole), (Format-Cell $row.plannerSignalCount), (Format-Cell $row.queryCount), (Format-Cell $row.matchedFileCount), (Format-Cell $row.candidateSnippetCount), (Format-Cell $row.includedSnippetCount), (Format-Cell $row.contextPromptChars), (Format-Cell $row.targetContextChars), (Format-Cell $row.hasDeletionNeighborEvidence), (Format-Cell $row.hasImplementationEvidence)
    }
    ''
    '## 对照结论'
    ''
    foreach ($row in ($agentReplays | Where-Object {
        $_.supplementedPatchCount -gt 0 -and $_.verifiedPagedRead -eq $true
    } | Select-Object -First 30)) {
        '- {0} #{1} 的固定版本回放补齐 {2} 份 patch，并验证了分页读取。线上完成状态和读取结果见对应 Run。' -f $row.triggerType, $row.taskId, $row.supplementedPatchCount
    }
    foreach ($row in ($standardRuns | Where-Object {
        $_.zeroSnippetsAfterSearch -eq $true -or $_.zeroSnippetsWithCandidates -eq $true -or $_.overTarget -eq $true
    } | Select-Object -First 30)) {
        if ($row.zeroSnippetsAfterSearch -eq $true) {
            '- Standard #{0}（{1}）执行 {2} 次查询，保留 0 条引用片段。' -f $row.taskId, (Format-Cell $row.comparisonRole), $row.queryCount
        }
        if ($row.zeroSnippetsWithCandidates -eq $true) {
            '- Standard #{0}（{1}）有 {2} 条候选且保留 0 条，需核对排序和裁剪。' -f $row.taskId, (Format-Cell $row.comparisonRole), $row.candidateSnippetCount
        }
        if ($row.overTarget -eq $true) {
            '- Standard #{0}（{1}）Context Pack 实际 {2} 字符，超过 {3} 字符的裁剪目标。' -f $row.taskId, (Format-Cell $row.comparisonRole), $row.contextPromptChars, $row.targetContextChars
        }
    }
    ''
    '## 待复核的 Finding 变化'
    ''
    foreach ($row in ($findingReviewCandidates | Select-Object -First 30)) {
        '- 任务 #{0}，Run #{1} 的 {2} 条 Finding 在 Run #{3} 变为 {4} 条。建议核对原发现和本次证据。' -f $row.taskId, $row.baselineRunId, $row.baselineFindingCount, $row.candidateRunId, $row.candidateFindingCount
    }
    if ($findingReviewCandidates.Count -eq 0) { '本次未记录基线有 Finding、候选为零的可配对样本。' }
    ''
    '## 高风险 Finding 抽样复核'
    ''
    ('输入 {0} 条样本，可核对 {1} 条，字段未知 {2} 条。符合高风险、部分上下文且高置信条件的样本为 {3} 条。' -f $findingSampleCoverage.sampleCount, $findingSampleCoverage.measurableCount, $findingSampleCoverage.unknownCount, $findingSampleCoverage.candidateCount)
    foreach ($row in ($highRiskFindingCandidates | Select-Object -First 30)) {
        '- 任务 #{0}，Run {1}，Finding 索引 {2}（{3} / {4} / {5}），待人工核对。' -f $row.taskId, (Format-Cell $row.runId), $row.findingIndex, $row.severity, $row.contextStatus, $row.confidence
    }
    '该计数用于挑选人工复核样本。'
    ''
    '## 独立批次统计'
    ''
    '| 范围 | 任务 / Run | 首轮失败 / 受影响任务 / 恢复任务 / 已知 HTTP | 汇总轮次为零 / 用量缺失 / 有轮次事件的 Run |'
    '| --- | --- | --- | --- |'
    foreach ($row in ($historicalSignals | Select-Object -First 30)) {
        '| {0} | {1} / {2} | {3} / {4} / {5} / {6} | {7} / {8} / {9} |' -f $row.scope, (Format-Cell $row.taskCount), (Format-Cell $row.runCount), (Format-Cell $row.firstRequestFailureCount), (Format-Cell $row.affectedTaskCount), (Format-Cell $row.recoveredTaskCount), (Format-Cell $row.knownHttpStatusCount), (Format-Cell $row.summaryTurnZeroCount), (Format-Cell $row.summaryUsageMissingCount), (Format-Cell $row.turnEventsCoveredRunCount)
    }
    ''
    '每张明细表最多展示 30 条，完整记录见 `report.json`。Finding 数的变化用于抽样复核。'
)

$outputPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
$jsonPath = Join-Path $outputPath 'report.json'
$markdownPath = Join-Path $outputPath 'report.md'
if ($sourceFile.FullName -in @($jsonPath, $markdownPath)) { throw 'Output paths must differ from the input path.' }
$utf8 = [Text.UTF8Encoding]::new($false)
$jsonContent = ($report | ConvertTo-Json -Depth 12) + "`n"
$markdownContent = ($markdown -join "`n") + "`n"
$null = [IO.Directory]::CreateDirectory($outputPath)
[IO.File]::WriteAllText($jsonPath, $jsonContent, $utf8)
[IO.File]::WriteAllText($markdownPath, $markdownContent, $utf8)
Write-Output $jsonPath
Write-Output $markdownPath
