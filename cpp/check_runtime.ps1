# Проверяет runtime DLL рядом с exe и при наличии моделей запускает короткий CLI smoke.
param(
    [string]$ExeDir = "$PSScriptRoot\build-ctranslate2\Release",
    [switch]$RunSmoke
)

$ErrorActionPreference = "Stop"

function Test-RequiredDlls {
    param([string]$Directory)

    $required = @(
        "ctranslate2.dll",
        "openblas.dll",
        "libprotobuf.dll",
        "abseil_dll.dll"
    )
    $missing = @()
    foreach ($name in $required) {
        $path = Join-Path $Directory $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            $missing += $name
        }
    }
    if ($missing.Count -gt 0) {
        throw "Рядом с exe нет DLL: $($missing -join ', ') (каталог: $Directory)"
    }
    Write-Output "Runtime DLL на месте в $Directory"
}

function Invoke-OptionalSmoke {
    param(
        [string]$ExePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds
    )

    if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) {
        throw "Не найден исполняемый файл: $ExePath"
    }

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo.FileName = $ExePath
    $process.StartInfo.Arguments = ($Arguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $process.StartInfo.WorkingDirectory = Split-Path -LiteralPath $ExePath
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    $process.StartInfo.CreateNoWindow = $true
    [void]$process.Start()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { $process.Kill() } catch { }
        throw "$ExePath не завершился за $TimeoutSeconds с (возможен hang)"
    }
    $outText = $process.StandardOutput.ReadToEnd()
    $errText = $process.StandardError.ReadToEnd()
    $exitCode = $process.ExitCode
    if ($exitCode -ne 0) {
        throw "$ExePath завершился с кодом $exitCode. stderr: $errText stdout: $outText"
    }
    if ([string]::IsNullOrWhiteSpace($outText)) {
        throw "$ExePath вернул пустой stdout"
    }
    $combined = "$outText`n$errText"
    if ($combined -match "Bad memory unallocation") {
        Write-Warning "Известное предупреждение выгрузки OpenBLAS (не ошибка перевода)"
    }
    Write-Output $outText.Trim()
}

try {
    if (-not (Test-Path -LiteralPath $ExeDir -PathType Container)) {
        throw "Каталог сборки не найден: $ExeDir"
    }

    Test-RequiredDlls -Directory $ExeDir

    if (-not $RunSmoke) {
        exit 0
    }

    $nllbRoot = Join-Path $HOME ".local\share\offline-translator\nllb-200"
    $argosRoot = Join-Path $HOME ".local\share\argos-translate\packages"

    if (Test-Path -LiteralPath (Join-Path $nllbRoot "nllb-200-distilled-600M\model.bin")) {
        Write-Output "=== NLLB smoke ==="
        Invoke-OptionalSmoke -ExePath (Join-Path $ExeDir "nllb_smoke.exe") `
            -Arguments @($nllbRoot) -TimeoutSeconds 30 | Out-Host
    } else {
        Write-Output "NLLB-модель не найдена, smoke пропущен: $nllbRoot"
    }

    if (Test-Path -LiteralPath $argosRoot -PathType Container) {
        $argosPackage = Get-ChildItem -LiteralPath $argosRoot -Directory `
            -Filter "translate-en_ru-*" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($argosPackage) {
            Write-Output "=== Argos smoke ==="
            Invoke-OptionalSmoke -ExePath (Join-Path $ExeDir "argos_smoke.exe") `
                -Arguments @($argosRoot) -TimeoutSeconds 30 | Out-Host
        } else {
            Write-Output "Пакет Argos en->ru не найден, smoke пропущен: $argosRoot"
        }
    } else {
        Write-Output "Каталог пакетов Argos не найден, smoke пропущен: $argosRoot"
    }

    exit 0
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
