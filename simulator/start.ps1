$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    python -X utf8 server.py --port 8766
} finally {
    Pop-Location
}
