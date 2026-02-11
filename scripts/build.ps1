param(
  [Parameter(Mandatory=$true)][string]$MainC,
  [string]$OutExe = "",
  [ValidateSet("msvc","clang-cl")][string]$Toolchain = "msvc",
  [ValidateSet("run","test")][string]$Mode = "run",
  [switch]$KeepC,
  [switch]$NoKeepC,
  [string]$CopyCToDir = "",
  [switch]$CleanBuildDir
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Ensure-Dir([string]$p) {
  $d = Split-Path -Parent $p
  if ($d -and !(Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
}

$MainCFull = (Resolve-Path $MainC).Path
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeC = Join-Path $RepoRoot "runtime\runtime.c"
$RuntimeInc = Join-Path $RepoRoot "runtime"
if (!(Test-Path $RuntimeC)) { throw "runtime.c not found: $RuntimeC" }

$MainDir = Split-Path -Parent $MainCFull
$MainDirName = Split-Path -Leaf $MainDir
$ProgName = $MainDirName
if ($ProgName.StartsWith("pcc_")) { $ProgName = $ProgName.Substring(4) }

if ([string]::IsNullOrWhiteSpace($OutExe)) {
  if ($Mode -eq "test") {
    $OutExe = Join-Path $RepoRoot ("build\test_out\" + $ProgName + ".exe")
  } else {
    $OutExe = Join-Path (Get-Location).Path ($ProgName + ".exe")
  }
}

if ($Mode -eq "test") {
  if (-not $KeepC.IsPresent -and -not $NoKeepC.IsPresent) { $KeepC = $true }
} else {
  if (-not $KeepC.IsPresent -and -not $NoKeepC.IsPresent) { $KeepC = $false }
}
if ($NoKeepC.IsPresent) { $KeepC = $false }

Ensure-Dir $OutExe

Write-Host "[build] Mode=$Mode"
Write-Host "[build] Toolchain=$Toolchain"
Write-Host "[build] MainC=$MainCFull"
Write-Host "[build] OutExe=$OutExe"

if ($CopyCToDir) {
  if (!(Test-Path $CopyCToDir)) { New-Item -ItemType Directory -Force -Path $CopyCToDir | Out-Null }
  Copy-Item -Force $MainCFull (Join-Path $CopyCToDir ($ProgName + ".c"))
}

if ($Toolchain -eq "msvc") {
  if (!(Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    throw "cl.exe not found."
  }
  & cl.exe /nologo /O2 /W3 /TC /I "$RuntimeInc" "$MainCFull" "$RuntimeC" /link /OUT:"$OutExe" | Write-Host
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
elseif ($Toolchain -eq "clang-cl") {
  $clang = Get-Command clang-cl.exe -ErrorAction SilentlyContinue
  if (-not $clang) { $clang = Get-Command clang-cl -ErrorAction SilentlyContinue }
  if (-not $clang) {
    throw "clang-cl not found. Install LLVM (winget install LLVM.LLVM)."
  }
  & $clang.Source /nologo /O2 /W3 /TC /I "$RuntimeInc" "$MainCFull" "$RuntimeC" /link /OUT:"$OutExe" | Write-Host
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
else { throw "Unknown toolchain: $Toolchain" }

if (-not $KeepC.IsPresent) {
  Remove-Item -Force -ErrorAction SilentlyContinue $MainCFull | Out-Null
}

if ($CleanBuildDir.IsPresent) {
  if ($MainDirName.StartsWith("pcc_")) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $MainDir | Out-Null
  }
}

exit 0