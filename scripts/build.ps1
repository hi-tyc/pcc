param(
  [Parameter(Mandatory=$true)][string]$MainC,
  [Parameter(Mandatory=$true)][string]$OutExe,
  [ValidateSet("msvc","clang-cl")][string]$Toolchain = "msvc"
)

$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$p) {
  $d = Split-Path -Parent $p
  if ($d -and !(Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeC = Join-Path $RepoRoot "runtime\runtime.c"
$RuntimeInc = Join-Path $RepoRoot "runtime"

if (!(Test-Path $MainC)) { throw "MainC not found: $MainC" }
if (!(Test-Path $RuntimeC)) { throw "runtime.c not found: $RuntimeC" }

Ensure-Dir $OutExe

Write-Host "[build] Toolchain=$Toolchain"
Write-Host "[build] MainC=$MainC"
Write-Host "[build] OutExe=$OutExe"

if ($Toolchain -eq "msvc") {
  if (!(Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    throw "cl.exe not found. Open 'Developer PowerShell for VS' or install VS Build Tools."
  }

  # /TC = compile as C
  # /I runtime include
  # /Fe sets output exe name
  & cl.exe /nologo /O2 /W3 /TC /I "$RuntimeInc" "$MainC" "$RuntimeC" /link /OUT:"$OutExe" | Write-Host
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  exit 0
}

if ($Toolchain -eq "clang-cl") {
  $clang = Get-Command clang-cl.exe -ErrorAction SilentlyContinue
  if (-not $clang) { $clang = Get-Command clang-cl -ErrorAction SilentlyContinue }
  if (-not $clang) {
    throw "clang-cl not found. Install LLVM (winget install LLVM.LLVM)."
  }

  # clang-cl uses MSVC-like flags; linking may require Windows SDK libs on your machine.
  & $clang.Source /nologo /O2 /W3 /TC /I "$RuntimeInc" "$MainC" "$RuntimeC" /link /OUT:"$OutExe" | Write-Host
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  exit 0
}

throw "Unknown toolchain: $Toolchain"