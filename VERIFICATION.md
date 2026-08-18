# VERIFICATION.md

## Purpose

Define verification expectations for 06_Stock baseline automation.

## Standard Local Verification

For behavior changes, use the OS-local virtual environment and temp roots. This
is the canonical local verification command sequence; other documents should
link here instead of defining a different pytest invocation.

```powershell
$ErrorActionPreference = "Stop"
$RepoRoot = (git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($RepoRoot)) {
    throw "could not resolve the Git worktree root"
}
$VenvPython = Join-Path $env:LOCALAPPDATA "06_Stock\.venv\Scripts\python.exe"
$env:STOCK_PYTEST_TMPDIR = Join-Path $env:LOCALAPPDATA "06_Stock\pytest_tmp_cases"
$PytestBaseTmp = Join-Path $env:LOCALAPPDATA "06_Stock\pytest_tmp_pytest"
$NodeCommand = Get-Command node -CommandType Application -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "OS-local venv Python not found: $VenvPython"
}
if ($null -eq $NodeCommand) {
    throw "Node.js is required for the QuickAdd contract verification"
}

& $NodeCommand.Source --check (Join-Path $RepoRoot "00_Config\QuickAdd\Stock_Command_Center.js")
if ($LASTEXITCODE -ne 0) { throw "QuickAdd JavaScript syntax check failed with exit $LASTEXITCODE" }

Set-Location (Join-Path $RepoRoot "70_Imports\scripts")
& $VenvPython -B -m pytest -p no:cacheprovider --basetemp $PytestBaseTmp
if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit $LASTEXITCODE" }

Set-Location $RepoRoot
& $VenvPython -B scripts\quality_gate.py
if ($LASTEXITCODE -ne 0) { throw "quality gate failed with exit $LASTEXITCODE" }

$RepoCaches = @(
    Get-ChildItem -LiteralPath $RepoRoot -Recurse -Force -ErrorAction Stop |
        Where-Object {
            $_.Name -eq "__pycache__" -or
            $_.Name -eq ".pytest_cache" -or
            (-not $_.PSIsContainer -and $_.Extension -eq ".pyc")
        }
)
if ($RepoCaches.Count -ne 0) {
    throw "repository Python cache artifacts found: $($RepoCaches.Count)"
}

git diff --check
if ($LASTEXITCODE -ne 0) { throw "git diff --check failed with exit $LASTEXITCODE" }
git status --short --branch
if ($LASTEXITCODE -ne 0) { throw "git status failed with exit $LASTEXITCODE" }
```

The quality gate runs the import pipeline against the repository baseline,
executes pytest, checks raw immutability, checks generated Markdown outside-block
preservation, validates processed output contracts, and scans generated Markdown
AUTO-GENERATED blocks for sensitive-pattern candidates.

Node.js is a required verification dependency because pytest executes the
QuickAdd JavaScript report contract. Missing Node.js is a verification failure,
not a skipped or passing QuickAdd check.

## Docs-Only Verification

For a scoped docs-only contract change, the minimum acceptable verification is:

```powershell
$ErrorActionPreference = "Stop"
git status --short --branch
if ($LASTEXITCODE -ne 0) { throw "git status failed with exit $LASTEXITCODE" }
git diff --check
if ($LASTEXITCODE -ne 0) { throw "git diff --check failed with exit $LASTEXITCODE" }
```

Then review changed files against:

- `PROJECT_BOUNDARY.md`
- `DATA_SCOPE.md`
- `SAFETY_POLICY.md`
- `APPROVALS.md`

If tests or the quality gate are not run for docs-only work, report them as
`NOT RUN` with a reason. Do not imply they passed.

## Live-Vault Dry-Run Verification

Before any actual live-vault write:

1. Verify the baseline repository first.
2. Run the import entrypoint with `--dry-run`.
3. Write dry-run evidence outside this repository, outside the live vault, and
   outside Google Drive synced folders.
4. Review expected file changes.
5. Confirm no private raw values are copied into closeout.

Dry-run evidence is a precondition for actual live writes. It is not itself
approval for the write.

## Actual Live Write Verification

Actual live writes require matching evidence and all live-write confirmation
flags enforced by `70_Imports/scripts/main.py`.

Closeout must report:

- baseline verification result;
- dry-run evidence path class, not private contents;
- expected changes reviewed;
- actual live-write command status;
- changed live-vault path summary;
- safety checks;
- risks and assumptions.

## NOT RUN Principle

If a check was not executed, mark it `NOT RUN` and explain why. Do not mark
unrun checks as passing.

## Safety Pattern Interpretation

Policy wording such as `password`, `token`, `account`, `broker`, or `API key`
inside safety rules is not automatically a secret leak. A private value or
assignment is the stop condition. Report possible private values without
printing them.
