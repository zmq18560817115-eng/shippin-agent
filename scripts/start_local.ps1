param(
    [string]$EnvFile = ".env.local",
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root $EnvFile

if (Test-Path -LiteralPath $envPath) {
    foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $pair = $trimmed.Split("=", 2)
        if ($pair.Count -ne 2) { throw "Invalid environment line: $line" }
        [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim(), "Process")
    }
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

$hostName = if ($env:VAF_HOST) { $env:VAF_HOST } else { "127.0.0.1" }
$port = if ($env:VAF_PORT) { $env:VAF_PORT } else { "8790" }
$missing = @("DOUBAO_API_KEY", "SEEDANCE_API_KEY") | Where-Object {
    -not [Environment]::GetEnvironmentVariable($_, "Process")
}
$mode = if ($missing.Count -eq 0) { "real-ready" } else { "mock-only" }
Write-Host "Starting video-agent-factory at http://${hostName}:${port} ($mode)"
if ($missing.Count -gt 0) { Write-Warning "Missing local variables: $($missing -join ', ')" }

$arguments = @("-m", "uvicorn", "orchestrator.api:app", "--host", $hostName, "--port", $port)
if ($Reload) { $arguments += "--reload" }
& $python @arguments
