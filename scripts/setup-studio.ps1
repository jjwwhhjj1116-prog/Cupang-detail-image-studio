param(
    [string]$StudioRoot = (Join-Path $PSScriptRoot '..'),
    [string]$PythonExe,
    [string]$NodeExe,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path -LiteralPath $StudioRoot).Path
$runtimePath = Join-Path $repoPath '.local/runtime.json'
$previousPath = $env:PATH
$previousPythonUtf8 = $env:PYTHONUTF8
try {
    $env:PYTHONUTF8 = '1'
    foreach ($binary in @($PythonExe, $NodeExe)) {
        if ($binary) {
            $resolvedBinary = (Resolve-Path -LiteralPath $binary).Path
            $env:PATH = (Split-Path -Parent $resolvedBinary) + [IO.Path]::PathSeparator + $env:PATH
        }
    }
    if ($CheckOnly) {
        if (-not (Test-Path -LiteralPath $runtimePath)) {
            throw 'No runtime manifest. Run scripts/setup-studio.ps1 once before using -CheckOnly.'
        }
    } else {
        & (Join-Path $repoPath 'scripts/setup-portable-tools.ps1') -StudioRoot $repoPath | Out-Host
    }
    $runtime = Get-Content -LiteralPath $runtimePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = $runtime.python.path
    $node = $runtime.node.path
    $npm = $runtime.node.npm
    foreach ($binary in @($python, $node, $npm)) {
        if (-not (Test-Path -LiteralPath $binary)) { throw 'Runtime manifest contains a missing executable. Run setup again.' }
    }
    $env:PATH = (Split-Path -Parent $node) + [IO.Path]::PathSeparator + $env:PATH
    if (-not $CheckOnly) {
        & $python -X utf8 (Join-Path $repoPath 'scripts/setup_portability.py') --repo $repoPath
        if ($LASTEXITCODE -ne 0) { throw 'PC workspace initialization failed.' }
        # Repository-scoped skills keep other projects and existing user skills intact.
        & $python -X utf8 (Join-Path $repoPath 'scripts/setup-remotion-skills.py') --dest (Join-Path $repoPath '.agents/skills')
        if ($LASTEXITCODE -ne 0) { throw 'Pinned Remotion skill installation failed.' }
        & (Join-Path $repoPath 'scripts/setup-remotion.ps1') -Project (Join-Path $repoPath 'remotion') -NodeExe $node -NpmCmd $npm
        Push-Location -LiteralPath (Join-Path $repoPath 'remotion')
        try {
            & $node 'node_modules/@remotion/cli/remotion-cli.js' browser ensure --quiet
            if ($LASTEXITCODE -ne 0) { throw 'Local Remotion rendering browser setup failed.' }
        } finally { Pop-Location }
    }
    & $python -X utf8 (Join-Path $repoPath 'scripts/doctor.py') --repo $repoPath --output (Join-Path $repoPath '.local/doctor.json')
    if ($LASTEXITCODE -ne 0) { throw 'Local setup checks failed; inspect .local/doctor.json.' }
    Write-Host 'Local setup verified. Open this repository in Codex; verify image generation, Figma and Flow connections there.'
} finally {
    $env:PATH = $previousPath
    $env:PYTHONUTF8 = $previousPythonUtf8
}
