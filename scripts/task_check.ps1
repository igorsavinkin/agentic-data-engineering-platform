[CmdletBinding()]
param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    foreach ($arguments in @(
        @('-m', 'ruff', 'format', '--check', '.'),
        @('-m', 'ruff', 'check', '.'),
        @('-m', 'mypy'),
        @('-m', 'pytest'),
        @('scripts/verify_repository_structure.py')
    )) {
        & $Python @arguments
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
} finally {
    Pop-Location
}
