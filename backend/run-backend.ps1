# Load env from ..\.env and start backend (python app.py)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$envPath = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if (-not (Test-Path $envPath)) { Write-Error "'.env' not found at $envPath"; exit 1 }

# Load variables from lines like: export NAME=value
Get-Content $envPath | ForEach-Object {
  $line = $_.Trim()
  if ($line -and -not $line.StartsWith('#') -and $line -match '^export\s+([^=]+)=(.*)$') {
    $name = $matches[1].Trim()
    $value = $matches[2].Trim() -replace '^["'']|["'']$', ''
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
  }
}

# Prefer venv Python if available
$py = Join-Path (Split-Path $PSScriptRoot -Parent) "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py "app.py"