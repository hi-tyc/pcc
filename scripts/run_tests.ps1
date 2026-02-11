param(
  [ValidateSet("auto","msvc","clang-cl")][string]$Toolchain = "auto",
  [switch]$CompareWithPython = $true,
  [switch]$AlsoCheckExpected = $true,
  [switch]$KeepLogs = $false
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$TestsDir = Join-Path $RepoRoot "tests"
$OutDir = Join-Path $RepoRoot "build\test_out"
if (!(Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

function Normalize([string]$s) {
  return ($s -replace "`r`n", "`n").TrimEnd()
}

# IMPORTANT:
# All stdin MUST be fed via cmd.exe redirection to avoid BOM/encoding corruption.
function Run-CmdRedirect {
  param([string]$CmdLine, [string]$TempDir)
  $o = Join-Path $TempDir ([Guid]::NewGuid().ToString("N") + ".o")
  $e = Join-Path $TempDir ([Guid]::NewGuid().ToString("N") + ".e")
  cmd /c "$CmdLine 1> `"$o`" 2> `"$e`"" | Out-Null
  $outText = if (Test-Path $o) { Get-Content -Raw $o } else { "" }
  $errText = if (Test-Path $e) { Get-Content -Raw $e } else { "" }
  $r = @{
    ExitCode = $LASTEXITCODE
    Stdout   = $outText
    Stderr   = $errText
  }
  if (-not $KeepLogs) { Remove-Item -Force -ErrorAction SilentlyContinue $o,$e | Out-Null }
  return $r
}

Push-Location $RepoRoot
try {
  $tmpDir = Join-Path $OutDir "__tmp"
  if (!(Test-Path $tmpDir)) { New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null }

  $testFiles = Get-ChildItem $TestsDir -Filter "t*.py" | Sort-Object Name
  if ($testFiles.Count -lt 3) { throw "Expected at least 3 tests, found $($testFiles.Count)" }

  $passed = 0
  $failed = 0

  foreach ($t in $testFiles) {
    $name = [IO.Path]::GetFileNameWithoutExtension($t.Name)
    $expectedFile = Join-Path $TestsDir "$name.expected.txt"

    Write-Host ""
    Write-Host "==> [test] $name"

    if ($AlsoCheckExpected -and !(Test-Path $expectedFile)) {
      Write-Host "[test] FAIL $name (missing expected file)"
      Write-Host "Missing expected file: $expectedFile"
      $failed++
      continue
    }

    $exe = Join-Path $OutDir "$name.exe"
    & python -m pcc build $t.FullName -o $exe --toolchain $Toolchain
    if ($LASTEXITCODE -ne 0) { $failed++; continue }

    $inputFile = Join-Path $TestsDir "$name.input.txt"
    $exeCmd = if (Test-Path $inputFile) { "`"$exe`" < `"$inputFile`"" } else { "`"$exe`"" }
    $exeRun = Run-CmdRedirect -CmdLine $exeCmd -TempDir $tmpDir
    $actualStdoutN = Normalize $exeRun.Stdout
    $actualStderrN = Normalize $exeRun.Stderr
    $actualExit    = $exeRun.ExitCode

    $pyStdoutN = ""; $pyStderrN = ""; $pyExit = 0
    if ($CompareWithPython) {
      $pyCmd = if (Test-Path $inputFile) { "python `"$($t.FullName)`" < `"$inputFile`"" } else { "python `"$($t.FullName)`"" }
      $pyRun = Run-CmdRedirect -CmdLine $pyCmd -TempDir $tmpDir
      $pyStdoutN = Normalize $pyRun.Stdout
      $pyStderrN = Normalize $pyRun.Stderr
      $pyExit    = $pyRun.ExitCode
    }

    $expectedN = ""
    if ($AlsoCheckExpected) {
      $expectedN = Normalize (Get-Content -Raw $expectedFile)
    }

    $ok = $true
    if ($CompareWithPython) {
      if ($actualExit -ne $pyExit) { $ok = $false }
      if ($actualStdoutN -ne $pyStdoutN) { $ok = $false }
      if ($actualStderrN -ne $pyStderrN) { $ok = $false }
    }
    if ($AlsoCheckExpected) {
      if ($actualStdoutN -ne $expectedN) { $ok = $false }
    }

    if ($ok) {
      Write-Host "[test] PASS $name"
      $passed++
    } else {
      Write-Host "[test] FAIL $name"
      if ($CompareWithPython) {
        Write-Host "---- python exit ----"; Write-Host $pyExit
        Write-Host "---- exe exit ----";    Write-Host $actualExit
        Write-Host "---- python stdout ----"; Write-Host $pyStdoutN
        Write-Host "---- exe stdout ----";    Write-Host $actualStdoutN
        Write-Host "---- python stderr ----"; Write-Host $pyStderrN
        Write-Host "---- exe stderr ----";    Write-Host $actualStderrN
      }
      if ($AlsoCheckExpected) {
        Write-Host "---- expected stdout ----"; Write-Host $expectedN
        Write-Host "---- exe stdout ----";      Write-Host $actualStdoutN
        Write-Host "---- exe stderr ----";      Write-Host $actualStderrN
      }
      $failed++
    }
  }

  Write-Host ""
  Write-Host "[tests] passed=$passed failed=$failed"

  if ($failed -ne 0) { exit 1 }
  exit 0
}
finally {
  Pop-Location
}