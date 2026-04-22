param(
    [string] $EnvFile
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $repoRoot ".local\gitlab.env"
}

function Import-DotEnv {
    param([string] $Path)

    if (-not (Test-Path $Path)) {
        Write-Host "Env file was not found: $Path" -ForegroundColor Red
        Write-Host "Create it from examples\gitlab.env.example, then run again."
        exit 1
    }

    Get-Content -Path $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            return
        }

        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -le 0) {
            return
        }

        $key = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

function Require-Env {
    param([string] $Name)

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        Write-Host "Missing required env value: $Name" -ForegroundColor Red
        exit 1
    }
    return $value
}

function Invoke-Json {
    param(
        [string] $Method,
        [string] $Uri,
        [object] $Body,
        [hashtable] $Headers
    )

    try {
        if ($null -eq $Body) {
            return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers
        }

        return Invoke-RestMethod -Method $Method -Uri $Uri -ContentType "application/json" -Headers $Headers -Body ($Body | ConvertTo-Json -Depth 30)
    } catch {
        Write-Host "Request failed: $Method $Uri" -ForegroundColor Red
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            Write-Host $_.ErrorDetails.Message
        } else {
            Write-Host $_.Exception.Message
        }
        throw
    }
}

function Get-HttpStatusCode {
    param([object] $ErrorRecord)

    if ($ErrorRecord.Exception -and $ErrorRecord.Exception.Response) {
        return [int] $ErrorRecord.Exception.Response.StatusCode
    }
    return $null
}

Import-DotEnv $EnvFile

$gitlabBaseUrl = (Require-Env "GITLAB_BASE_URL").TrimEnd("/")
$gitlabToken = Require-Env "GITLAB_TOKEN"
$projectId = Require-Env "GITLAB_PROJECT_ID"
$mrIid = Require-Env "GITLAB_MR_IID"
$perPageValue = [Environment]::GetEnvironmentVariable("GITLAB_DIFF_PER_PAGE", "Process")
if ([string]::IsNullOrWhiteSpace($perPageValue)) {
    $perPageValue = "100"
}
$backendBaseUrl = [Environment]::GetEnvironmentVariable("BACKEND_BASE_URL", "Process")
if ([string]::IsNullOrWhiteSpace($backendBaseUrl)) {
    $backendBaseUrl = "http://localhost:8080"
}
$backendBaseUrl = $backendBaseUrl.TrimEnd("/")

Write-Host "Using env file: $EnvFile"
Write-Host "GitLab base URL: $gitlabBaseUrl"
Write-Host "GitLab project: $projectId"
Write-Host "GitLab MR iid: $mrIid"
Write-Host "Backend base URL: $backendBaseUrl"

Write-Host ""
Write-Host "Step 1/5: Checking backend health..."
$health = Invoke-Json -Method "GET" -Uri "$backendBaseUrl/api/health"
if ($health.success -ne $true -or $health.data.status -ne "UP") {
    Write-Host "Backend health check is not UP." -ForegroundColor Red
    $health | ConvertTo-Json -Depth 10
    exit 1
}
Write-Host "Backend is UP."

Write-Host ""
Write-Host "Step 2/5: Checking GitLab MR diffs API..."
$encodedProjectId = [uri]::EscapeDataString($projectId)
$encodedMrIid = [uri]::EscapeDataString($mrIid)
$diffUrl = "$gitlabBaseUrl/api/v4/projects/$encodedProjectId/merge_requests/$encodedMrIid/diffs?page=1&per_page=$perPageValue"
$diffSource = "diffs"
try {
    $diffs = Invoke-Json -Method "GET" -Uri $diffUrl -Headers @{ "PRIVATE-TOKEN" = $gitlabToken }
} catch {
    if ((Get-HttpStatusCode $_) -ne 404) {
        throw
    }
    Write-Host "GitLab /diffs endpoint returned 404; falling back to /changes..."
    $changesUrl = "$gitlabBaseUrl/api/v4/projects/$encodedProjectId/merge_requests/$encodedMrIid/changes"
    $changesResponse = Invoke-Json -Method "GET" -Uri $changesUrl -Headers @{ "PRIVATE-TOKEN" = $gitlabToken }
    $diffs = $changesResponse.changes
    $diffSource = "changes"
}
if ($null -eq $diffs -or $diffs.Count -eq 0) {
    Write-Host "GitLab MR diff API returned no files." -ForegroundColor Red
    exit 1
}
Write-Host "GitLab returned $($diffs.Count) diff file(s) via /$diffSource."

Write-Host ""
Write-Host "Step 3/5: Sending webhook payload without changedFiles..."
$now = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
$payload = [ordered]@{
    object_kind = "merge_request"
    event_type = "merge_request"
    event_time = $now
    project = [ordered]@{
        id = $projectId
        name = "gitlab-project-$projectId"
        web_url = $gitlabBaseUrl
    }
    object_attributes = [ordered]@{
        iid = $mrIid
        action = "open"
        source_branch = "feature/gitlab-diff-validation"
        target_branch = "main"
        url = "$gitlabBaseUrl/-/merge_requests/$mrIid"
        updated_at = $now
        last_commit = [ordered]@{
            id = "manual-gitlab-validation"
        }
    }
    user = [ordered]@{
        name = "GitLab Validation"
        username = "gitlab-validation"
    }
}

$webhookResponse = Invoke-Json `
    -Method "POST" `
    -Uri "$backendBaseUrl/api/webhooks/gitlab/merge-request" `
    -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
    -Body $payload

if ($webhookResponse.success -ne $true) {
    Write-Host "Webhook response was not successful." -ForegroundColor Red
    $webhookResponse | ConvertTo-Json -Depth 20
    exit 1
}
$taskId = $webhookResponse.data.taskId
Write-Host "Webhook task created: $taskId"

Write-Host ""
Write-Host "Step 4/5: Checking task detail..."
$taskDetail = Invoke-Json -Method "GET" -Uri "$backendBaseUrl/api/review-tasks/$taskId"
$source = $taskDetail.data.changedFilesSummary.source
$count = $taskDetail.data.changedFilesSummary.count
if ($source -ne "gitlab_api") {
    Write-Host "Expected changedFilesSummary.source=gitlab_api, got: $source" -ForegroundColor Red
    $taskDetail | ConvertTo-Json -Depth 30
    exit 1
}
if ($count -le 0) {
    Write-Host "Expected changedFilesSummary.count > 0, got: $count" -ForegroundColor Red
    exit 1
}
Write-Host "Task status: $($taskDetail.data.status)"
Write-Host "Changed files source: $source"
Write-Host "Changed files count: $count"

Write-Host ""
Write-Host "Step 5/5: Checking risk result..."
$result = Invoke-Json -Method "GET" -Uri "$backendBaseUrl/api/review-tasks/$taskId/result"
if ($result.success -ne $true -or $null -eq $result.data.riskCard) {
    Write-Host "Risk result is missing." -ForegroundColor Red
    $result | ConvertTo-Json -Depth 30
    exit 1
}

Write-Host ""
Write-Host "GitLab validation passed." -ForegroundColor Green
[PSCustomObject]@{
    taskId = $taskId
    taskStatus = $taskDetail.data.status
    changedFilesSource = $source
    changedFilesCount = $count
    riskLevel = $result.data.riskLevel
    riskItemCount = $result.data.riskItemCount
    changeTypes = ($result.data.changeAnalysis.changeTypes -join ",")
} | ConvertTo-Json -Depth 10
