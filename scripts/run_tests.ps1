param(
  [ValidateSet("auto","msvc","clang-cl")][string]$Toolchain = "auto"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$TestsDir = Join-Path $RepoRoot "tests\fixtures"
$OutDir = Join-Path $RepoRoot "build\test_out"
if (!(Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

function Normalize([string]$s) {
  # normalize CRLF -> LF and trim trailing whitespace at end
  return ($s -replace "`r`n", "`n").TrimEnd()
}

$testFiles = Get-ChildItem $TestsDir -Filter "t*.py" | Sort-Object Name

if ($testFiles.Count -lt 3) {
  throw "Expected at least 3 tests, found $($testFiles.Count)"
}

$passed = 0
$failed = 0

foreach ($t in $testFiles) {
  $name = [IO.Path]::GetFileNameWithoutExtension($t.Name)
  $expectedFile = Join-Path $TestsDir "$name.expected.txt"
  if (!(Test-Path $expectedFile)) { throw "Missing expected file: $expectedFile" }

  $exe = Join-Path $OutDir "$name.exe"

  Write-Host ""
  Write-Host "==> [test] $name"

  & python -m pcc build $t.FullName -o $exe --toolchain $Toolchain
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[test] build failed: $name"
    $failed++
    continue
  }

  $actual = & $exe | Out-String
  $actualN = Normalize $actual
  $expectedN = Normalize (Get-Content -Raw $expectedFile)

  if ($actualN -eq $expectedN) {
    Write-Host "[test] PASS $name"
    $passed++
  } else {
    Write-Host "[test] FAIL $name"
    Write-Host "---- expected ----"
    Write-Host $expectedN
    Write-Host "---- actual ----"
    Write-Host $actualN
    $failed++
  }
}

Write-Host ""
Write-Host "[tests] passed=$passed failed=$failed"

if ($failed -ne 0) { exit 1 }
exit 0