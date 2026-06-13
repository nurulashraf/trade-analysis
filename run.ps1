#Requires -Version 5.1
# Windows equivalent of run.sh: cd to project root, load .env, start the server.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Load .env if present (KEY=value lines; blank lines and # comments ignored)
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        $line = $line.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { continue }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { continue }
        $key   = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        # Strip surrounding quotes, if any
        if ($value.Length -ge 2 -and
            (($value.StartsWith('"') -and $value.EndsWith('"')) -or
             ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

$port = if ($env:PORT) { $env:PORT } else { "8000" }

# Prefer the project venv if it exists (so double-clicking run.bat just works)
$venvUvicorn = Join-Path $PSScriptRoot ".venv\Scripts\uvicorn.exe"
if (Test-Path $venvUvicorn) {
    & $venvUvicorn backend.main:app --host 0.0.0.0 --port $port
} else {
    uvicorn backend.main:app --host 0.0.0.0 --port $port
}
