param(
    [string]$StudioRoot = (Join-Path $PSScriptRoot '..'),
    [switch]$Offline
)
# Immutable FFmpeg release, shared checksum/cache checks, no machine-wide changes.
$ErrorActionPreference = 'Stop'
$mediaRoot = [IO.Path]::GetFullPath($StudioRoot)
$mediaOffline = $Offline
. (Join-Path $PSScriptRoot 'setup-portable-tools.ps1') -FunctionsOnly
$mediaLock = Get-Content -LiteralPath (Join-Path $mediaRoot 'config/toolchain.lock.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Initialize-StudioMedia $mediaRoot $mediaLock -Offline:$mediaOffline | Out-Null
Get-Content -LiteralPath (Join-Path $mediaRoot '.tools/media-tools.json') -Raw -Encoding UTF8
