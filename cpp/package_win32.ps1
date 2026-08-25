param(
    [string]$BuildDir = "$PSScriptRoot\build-win32",
    [string]$CTranslate2Dir = "C:\deps\CTranslate2\build-openblas-noomp\Release",
    [string]$OutputDir = "$PSScriptRoot\portable-win32",
    [switch]$IncludeModels
)

$ErrorActionPreference = "Stop"

function Copy-RequiredFile {
    param(
        [string]$Source,
        [string]$TargetDirectory
    )

    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Required file was not found: $Source"
    }
    Copy-Item -LiteralPath $Source -Destination $TargetDirectory -Force
}

try {
    $vcpkgBin = Join-Path $BuildDir "vcpkg_installed\x64-windows\bin"
    $exe = Join-Path $BuildDir "Release\offline_translator_win32.exe"
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "Build offline_translator_win32 Release first: $exe"
    }

    if (Test-Path -LiteralPath $OutputDir) {
        Remove-Item -LiteralPath $OutputDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
    Copy-RequiredFile $exe $OutputDir
    Copy-RequiredFile (Join-Path $CTranslate2Dir "ctranslate2.dll") $OutputDir
    Copy-RequiredFile "C:\vcpkg\installed\x64-windows\bin\openblas.dll" $OutputDir

    foreach ($name in @("libprotobuf.dll", "abseil_dll.dll")) {
        Copy-RequiredFile (Join-Path $vcpkgBin $name) $OutputDir
    }

    if ($IncludeModels) {
        $dataDir = Join-Path $OutputDir "data"
        New-Item -ItemType Directory -Path $dataDir | Out-Null
        $argosSource = Join-Path $HOME ".local\share\argos-translate\packages"
        $nllbSource = Join-Path $HOME ".local\share\offline-translator\nllb-200"
        if (Test-Path -LiteralPath $argosSource -PathType Container) {
            Copy-Item -LiteralPath $argosSource -Destination (Join-Path $dataDir "argos-packages") -Recurse
        }
        if (Test-Path -LiteralPath $nllbSource -PathType Container) {
            Copy-Item -LiteralPath $nllbSource -Destination (Join-Path $dataDir "nllb-200") -Recurse
        }
    }

    Write-Output "Package ready: $OutputDir"
} catch {
    Write-Error "Packaging error: $($_.Exception.Message)"
    exit 1
}
