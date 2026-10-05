param(
    [string]$Project = (Join-Path $PSScriptRoot '../remotion'),
    [string]$NodeExe = 'node.exe',
    [string]$NpmCmd = 'npm.cmd'
)
$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path -LiteralPath $Project).Path
Push-Location -LiteralPath $projectPath
try {
    $lockPath = Join-Path $projectPath 'package-lock.json'
    $stampPath = Join-Path $projectPath 'node_modules/.detail-studio-install.json'
    $lockStream = [IO.File]::OpenRead($lockPath)
    $lockHasher = [Security.Cryptography.SHA256]::Create()
    try { $lockHash = ([BitConverter]::ToString($lockHasher.ComputeHash($lockStream))).Replace('-', '').ToLowerInvariant() }
    finally { $lockStream.Dispose(); $lockHasher.Dispose() }
    $installed = $false
    if (Test-Path -LiteralPath $stampPath) {
        $stamp = Get-Content -LiteralPath $stampPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $installed = ($stamp.lock_sha256 -eq $lockHash) -and (Test-Path -LiteralPath 'node_modules/@remotion/cli/remotion-cli.js')
    }
    # Adopt a valid installation made before this bootstrap existed, without npm ci
    # removing binaries that may be used by an already running Studio preview.
    if (-not (Test-Path -LiteralPath $stampPath)) {
        $installed = Test-Path -LiteralPath 'node_modules/@remotion/cli/remotion-cli.js'
    }
    if ($installed) {
        $packages = Get-Content -LiteralPath 'package.json' -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($group in @($packages.dependencies, $packages.devDependencies)) {
            foreach ($dependency in $group.PSObject.Properties) {
                $packageFile = Join-Path 'node_modules' (Join-Path $dependency.Name 'package.json')
                if (-not (Test-Path -LiteralPath $packageFile)) { $installed = $false; break }
                $actual = Get-Content -LiteralPath $packageFile -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($actual.version -ne $dependency.Value) { $installed = $false; break }
            }
        }
    }
    if (-not $installed) {
        & $NpmCmd ci --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Remotion dependency installation failed.' }
    }
    & $NodeExe 'node_modules/@remotion/cli/remotion-cli.js' versions
    if ($LASTEXITCODE -ne 0) { throw 'Remotion version validation failed.' }
    $stamp = @{ lock_sha256 = $lockHash; runtime_version = '4.0.533' } | ConvertTo-Json
    [IO.File]::WriteAllText($stampPath, $stamp, (New-Object Text.UTF8Encoding $false))
    Write-Host 'Local Remotion runtime installed. Use npm run dev to open Studio.'
} finally { Pop-Location }
