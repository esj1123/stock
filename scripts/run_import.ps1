#requires -Version 5.1
<#
.SYNOPSIS
  Runs the Stock vault import pipeline on Windows.

.DESCRIPTION
  Creates a repo-root .venv if needed, installs import requirements, and
  delegates to the standard entrypoint: 70_Imports/scripts/main.py.

  If no action is provided, the script defaults to "all". Supported actions are
  import, report, qa, and all. Additional arguments are passed through to main.py.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_import.ps1 all --dry-run

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_import.ps1 qa
#>

[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$RemainingArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$VenvDir = Join-Path $RootDir ".venv"
$ReqFile = Join-Path $RootDir "70_Imports\scripts\requirements.txt"
$MainPy = Join-Path $RootDir "70_Imports\scripts\main.py"

$Python = $null
foreach ($Candidate in @("python", "py")) {
  if (-not (Get-Command $Candidate -ErrorAction SilentlyContinue)) {
    continue
  }

  & $Candidate --version *> $null
  if ($LASTEXITCODE -eq 0) {
    $Python = $Candidate
    break
  }
}

if (-not $Python) {
  throw "No working Python launcher found. Install Python or make the 'py' launcher available."
}

if (-not (Test-Path -LiteralPath $VenvDir)) {
  & $Python -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

& $VenvPython -m pip install -r $ReqFile

$Actions = @("import", "report", "qa", "all")
$HasAction = $false
foreach ($Arg in $RemainingArgs) {
  if ($Actions -contains $Arg) {
    $HasAction = $true
    break
  }
}

$MainArgs = if ($HasAction) { $RemainingArgs } else { @("all") + $RemainingArgs }

& $VenvPython $MainPy @MainArgs
