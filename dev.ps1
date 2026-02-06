<#
.SYNOPSIS
Helper script for AuditorIA External API Service development.

.DESCRIPTION
Simplifies running the server, running tests, and managing dependencies.

.EXAMPLE
.\dev.ps1 -Run
Runs the development server.

.EXAMPLE
.\dev.ps1 -Test
Runs the test suite.
#>

param (
    [switch]$Run,
    [switch]$Test,
    [switch]$Install
)

if ($Install) {
    Write-Host "Installing dependencies..." -ForegroundColor Green
    pip install -r requirements.txt
}

if ($Test) {
    Write-Host "Running tests..." -ForegroundColor Green
    pytest tests/ -v
}

if ($Run) {
    Write-Host "Starting development server..." -ForegroundColor Green
    uvicorn app.main:app --reload --port 8001
}

if (-not ($Run -or $Test -or $Install)) {
    Write-Host "Usage: .\dev.ps1 [-Run] [-Test] [-Install]" -ForegroundColor Yellow
}
