#requires -Version 5.1
<#
.SYNOPSIS
  Runs the Stock vault import pipeline on Windows.

.DESCRIPTION
  Creates a local virtual environment outside the repo/Vault by default,
  installs import requirements, and delegates to the standard entrypoint:
  70_Imports/scripts/main.py.

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

# Keep the virtual environment outside the repository and outside Google Drive
# synced Vaults by default so dependency files are never mixed with live data.
$ConfiguredVenvDir = [Environment]::GetEnvironmentVariable("STOCK_VENV_DIR")
if ([string]::IsNullOrWhiteSpace($ConfiguredVenvDir)) {
  $LocalAppData = $env:LOCALAPPDATA
  if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
    $LocalAppData = [Environment]::GetFolderPath("LocalApplicationData")
  }
  if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
    throw "LOCALAPPDATA is not available. Set STOCK_VENV_DIR to a local virtual environment path."
  }
  $VenvDir = Join-Path $LocalAppData "06_Stock\.venv"
}
else {
  $VenvDir = $ConfiguredVenvDir
}

$VenvParent = Split-Path -Parent $VenvDir
if ($VenvParent -and -not (Test-Path -LiteralPath $VenvParent)) {
  New-Item -ItemType Directory -Path $VenvParent -Force | Out-Null
}

$ReqFile = Join-Path $RootDir "70_Imports\scripts\requirements.txt"
$MainPy = Join-Path $RootDir "70_Imports\scripts\main.py"

$Python = $null
foreach ($Candidate in @("py", "python")) {
  $Command = Get-Command $Candidate -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $Command) {
    continue
  }

  if ($Command.Source -and ($Command.Source -like "*\WindowsApps\python.exe")) {
    continue
  }

  try {
    & $Candidate --version *> $null
    if ($LASTEXITCODE -eq 0) {
      $Python = $Candidate
      break
    }
  }
  catch {
    continue
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

[string[]]$MainArgs = @()
if ($HasAction) {
  $MainArgs = @($RemainingArgs)
}
else {
  $MainArgs = @("all") + @($RemainingArgs)
}

& $VenvPython $MainPy @MainArgs
exit $LASTEXITCODE
