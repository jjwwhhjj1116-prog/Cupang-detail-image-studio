param([string]$Project = (Join-Path $PSScriptRoot '../remotion'))
$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path -LiteralPath $Project).Path
Push-Location -LiteralPath $projectPath
try {
    & npm.cmd ci --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Remotion dependency installation failed.' }
    & node.exe 'node_modules/@remotion/cli/remotion-cli.js' versions
    if ($LASTEXITCODE -ne 0) { throw 'Remotion version validation failed.' }
    Write-Host 'Local Remotion runtime installed. Use npm run dev to open Studio.'
} finally { Pop-Location }
