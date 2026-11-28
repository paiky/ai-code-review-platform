function Resolve-StartupWorktree {
    param(
        [string] $ScriptDirectory,
        [string] $WorktreeBranch
    )

    $root = Split-Path -Parent $ScriptDirectory
    $git = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $git) {
        if ($WorktreeBranch) {
            throw "Git is required to select a worktree by branch."
        }
        return [pscustomobject]@{ Root = $root; Branch = "unknown" }
    }

    # Windows PowerShell must decode Git's paths and branch names as UTF-8.
    $previousEncoding = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        if (-not $WorktreeBranch) {
            $ErrorActionPreference = "SilentlyContinue"
            $branch = & $git.Source -C $root rev-parse --abbrev-ref HEAD 2>$null
            if ($LASTEXITCODE -ne 0) { $branch = "unknown" }
            return [pscustomobject]@{ Root = $root; Branch = $branch }
        }

        $entries = & $git.Source -C $root worktree list --porcelain
        if ($LASTEXITCODE -ne 0) {
            throw "Could not list Git worktrees for $root."
        }

        $matchesByBranch = @(foreach ($entry in $entries) {
            if ($entry.StartsWith('worktree ')) {
                $path = $entry.Substring('worktree '.Length)
            }
            elseif ($entry -ceq "branch refs/heads/$WorktreeBranch") {
                $path
            }
        })
        if ($matchesByBranch.Count -ne 1) {
            throw "Expected one checked-out worktree for branch '$WorktreeBranch'. Run 'git worktree list' to see the available branches."
        }
        $root = (Resolve-Path -LiteralPath $matchesByBranch[0]).Path
        if (-not (Test-Path -LiteralPath (Join-Path $root ".git"))) {
            throw "The registered worktree for '$WorktreeBranch' is unavailable: $root"
        }
        return [pscustomobject]@{ Root = $root; Branch = $WorktreeBranch }
    }
    finally {
        [Console]::OutputEncoding = $previousEncoding
    }
}
