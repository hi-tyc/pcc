param(
  [Parameter(Mandatory=$true)][string]$MainC,
  [Parameter(Mandatory=$true)][string]$OutExe,
  [ValidateSet("msvc","clang-cl")][string]$Toolchain = "msvc",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$p) {
  $d = Split-Path -Parent $p
  if ($d -and !(Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeInc = Join-Path $RepoRoot "runtime"

$RuntimeSources = @(
  "rt_bigint.c",
  "rt_string.c",
  "rt_error.c",
  "rt_exc.c",
  "rt_math.c",
  "rt_string_ex.c",
  "rt_list.c",
  "rt_dict.c"
) | ForEach-Object { Join-Path $RuntimeInc $_ }

if (!(Test-Path $MainC)) { throw "MainC not found: $MainC" }
foreach ($src in $RuntimeSources) {
  if (!(Test-Path $src)) { throw "Runtime source not found: $src" }
}

Ensure-Dir $OutExe

Write-Host "[build] Toolchain=$Toolchain"
Write-Host "[build] MainC=$MainC"
Write-Host "[build] OutExe=$OutExe"
Write-Host "[build] RuntimeInc=$RuntimeInc"

if ($Toolchain -eq "msvc") {
  if (!(Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    throw "cl.exe not found. Open 'Developer PowerShell for VS' or install VS Build Tools."
  }

  # /TC = compile as C
  # /I runtime include
  # /Fe sets output exe name
  $cmd = @(
    "cl.exe",
    "/nologo","/O2","/W3","/TC",
    "/I", "$RuntimeInc",
    "$MainC"
  ) + $RuntimeSources + @("/link", "/OUT:$OutExe")

  if ($DryRun) {
    Write-Host "[build] DRYRUN: $($cmd -join ' ')"
    exit 0
  }

  & cl.exe /nologo /O2 /W3 /TC /I "$RuntimeInc" "$MainC" @RuntimeSources /link /OUT:"$OutExe" | Write-Host
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
  if ($DryRun) {
    Write-Host "[build] DRYRUN: $($clang.Source) /nologo /O2 /W3 /TC /I $RuntimeInc $MainC $($RuntimeSources -join ' ') /link /OUT:$OutExe"
    exit 0
  }

  & $clang.Source /nologo /O2 /W3 /TC /I "$RuntimeInc" "$MainC" @RuntimeSources /link /OUT:"$OutExe" | Write-Host
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  exit 0
}

throw "Unknown toolchain: $Toolchain"