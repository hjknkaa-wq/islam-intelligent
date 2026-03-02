param(
  [Parameter(Position = 0)]
  [ValidateSet("safe", "balanced", "max-autonomy")]
  [string]$Profile = "balanced",
  [switch]$SkipDoctor
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$profilesDir = Join-Path $scriptRoot ".opencode\profiles"
$sourcePath = Join-Path $profilesDir "$Profile.jsonc"
$targetPath = Join-Path $scriptRoot ".opencode\oh-my-opencode.jsonc"

if (-not (Test-Path $sourcePath)) {
  Write-Error "Profile file not found: $sourcePath"
  exit 1
}

Copy-Item -Path $sourcePath -Destination $targetPath -Force
Write-Host "Applied profile: $Profile"
Write-Host "Active config: $targetPath"

if ($SkipDoctor) {
  exit 0
}

try {
  $doctorRaw = oh-my-opencode doctor --json
  $doctor = $doctorRaw | ConvertFrom-Json
  if ($doctor.exitCode -eq 0) {
    Write-Host ("Doctor: pass (passed={0}, warnings={1}, failed={2})" -f $doctor.summary.passed, $doctor.summary.warnings, $doctor.summary.failed)
  } else {
    Write-Warning "Doctor found issues. Run: oh-my-opencode doctor --verbose"
    exit 1
  }
} catch {
  Write-Warning "Could not parse doctor output. Run: oh-my-opencode doctor --verbose"
  exit 1
}
