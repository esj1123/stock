#requires -Version 5.1
<
.SYNOPSIS
  나무증권 엑셀 Import 실행 스크립트(Windows)

.DESCRIPTION
  - Vault 루트 기준으로 venv를 만들고(requirements 설치)
  - namoo_excel_import.py를 실행합니다.
  - 추가 인자(--dry-run 등)는 그대로 importer로 전달됩니다.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\run_import.ps1
  powershell -ExecutionPolicy Bypass -File scripts\run_import.ps1 --dry-run
>

[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Vault root = parent of this scripts\ directory
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$VenvDir  = Join-Path $RootDir "70_Imports\.venv"
$ReqFile  = Join-Path $RootDir "70_Imports\scripts\requirements.txt"
$Importer = Join-Path $RootDir "70_Imports\scripts\namoo_excel_import.py"

# Pick python launcher
$Python = "python"
try { & $Python --version | Out-Null } catch { $Python = "py" }

if (-not (Test-Path $VenvDir)) {
  & $Python -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r $ReqFile

# Run importer
& $VenvPython $Importer --create-companies @Args
