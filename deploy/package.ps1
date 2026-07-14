[CmdletBinding()]
param(
    [string]$OutputPath = "",
    [switch]$SkipBuild,
    [switch]$ListOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
if (-not $OutputPath) {
    $OutputPath = Join-Path $Root "klipklop-deploy.zip"
}
$Frontend = Join-Path $Root "frontend"
$Required = @("requirements.txt", "server.py", "frontend/dist/index.html", "deploy/klipklop.service", "deploy/Caddyfile")
$ExcludedDirectories = @(".git", ".venv", "venv", "node_modules", "data", "output", "out", "_temp", ".temp", "cache", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "dist-ssr")
$ExcludedFilePatterns = @(".env", ".env.*", "config.json", "cookie.txt", "cookies.txt", "client_secret*.json", "token*.json", "tickets.json", "upload_queue.json", "error.log", "*.log", "*.pyc", "*.pyo", "*.zip", "*.pem", "*.key", "*.p12", "*.pfx", "*.sqlite", "*.sqlite3", ".DS_Store")

function Get-RelativePath([string]$Path) {
    return $Path.Substring($Root.Length).TrimStart("\", "/").Replace("\", "/")
}

function Test-Excluded([string]$RelativePath) {
    $normalized = $RelativePath.Replace("\", "/")
    $segments = $normalized.Split("/")
    foreach ($segment in $segments) {
        if ($ExcludedDirectories -contains $segment) {
            return $true
        }
    }
    $name = [System.IO.Path]::GetFileName($normalized)
    foreach ($pattern in $ExcludedFilePatterns) {
        if ($name -like $pattern) {
            if ($name -like "*.env.example") {
                continue
            }
            return $true
        }
    }
    return $false
}

if (-not $SkipBuild) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm is required to build the frontend"
    }
    Push-Location $Frontend
    try {
        & npm ci
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci failed with exit code $LASTEXITCODE"
        }
        & npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "npm run build failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

$Files = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Force | ForEach-Object {
    $relative = Get-RelativePath $_.FullName
    if (-not (Test-Excluded $relative)) {
        [PSCustomObject]@{ FullName = $_.FullName; RelativePath = $relative }
    }
} | Sort-Object RelativePath)

foreach ($requiredPath in $Required) {
    if ($Files.RelativePath -notcontains $requiredPath) {
        throw "Required deployment file missing: $requiredPath"
    }
}

$Files.RelativePath
if ($ListOnly) {
    Write-Verbose "$($Files.Count) files selected"
    return
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
if ([System.IO.Path]::GetExtension($resolvedOutput) -ne ".zip") {
    throw "OutputPath must end in .zip"
}
$outputParent = Split-Path -Parent $resolvedOutput
if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
    throw "Output directory does not exist: $outputParent"
}
if (Test-Path -LiteralPath $resolvedOutput) {
    Remove-Item -LiteralPath $resolvedOutput -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$manifestLines = @("KLIPKLOP-DEPLOY-MANIFEST v1", "SHA256  PATH")
foreach ($file in $Files) {
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifestLines += "$hash  $($file.RelativePath)"
}
$manifest = ($manifestLines -join "`n") + "`n"
$fixedTime = [DateTimeOffset]::new(2000, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
$stream = [System.IO.File]::Open($resolvedOutput, [System.IO.FileMode]::CreateNew)
try {
    $archive = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        foreach ($file in $Files) {
            $entry = $archive.CreateEntry($file.RelativePath, [System.IO.Compression.CompressionLevel]::Optimal)
            $entry.LastWriteTime = $fixedTime
            $input = [System.IO.File]::OpenRead($file.FullName)
            $output = $entry.Open()
            try {
                $input.CopyTo($output)
            }
            finally {
                $output.Dispose()
                $input.Dispose()
            }
        }
        $manifestEntry = $archive.CreateEntry("DEPLOY-MANIFEST.txt", [System.IO.Compression.CompressionLevel]::Optimal)
        $manifestEntry.LastWriteTime = $fixedTime
        $writer = [System.IO.StreamWriter]::new($manifestEntry.Open(), [System.Text.UTF8Encoding]::new($false))
        try {
            $writer.Write($manifest)
        }
        finally {
            $writer.Dispose()
        }
    }
    finally {
        $archive.Dispose()
    }
}
finally {
    $stream.Dispose()
}

$validationStream = [System.IO.File]::OpenRead($resolvedOutput)
try {
    $validationArchive = [System.IO.Compression.ZipArchive]::new($validationStream, [System.IO.Compression.ZipArchiveMode]::Read, $false)
    try {
        $entryNames = @($validationArchive.Entries | ForEach-Object { $_.FullName })
        foreach ($requiredPath in $Required) {
            if ($entryNames -notcontains $requiredPath) {
                throw "Archive validation failed; missing: $requiredPath"
            }
        }
        foreach ($entryName in $entryNames) {
            if ($entryName -ne "DEPLOY-MANIFEST.txt" -and (Test-Excluded $entryName)) {
                throw "Archive validation failed; excluded path found: $entryName"
            }
        }
    }
    finally {
        $validationArchive.Dispose()
    }
}
finally {
    $validationStream.Dispose()
}

$archiveHash = (Get-FileHash -LiteralPath $resolvedOutput -Algorithm SHA256).Hash.ToLowerInvariant()
"Archive: $resolvedOutput"
"SHA256: $archiveHash"
"Files: $($Files.Count + 1)"
