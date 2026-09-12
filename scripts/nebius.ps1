# Invoke the official Nebius CLI installed in the current user's Ubuntu WSL home.
# Credentials remain managed by the CLI inside WSL, outside this repository.
$ErrorActionPreference = 'Stop'

$driftopsLinuxHome = (& wsl.exe --distribution Ubuntu --exec printenv HOME | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($driftopsLinuxHome)) {
    throw 'Unable to locate the Ubuntu WSL user home.'
}

$driftopsNebiusExecutable = "$driftopsLinuxHome/.nebius/bin/nebius"
& wsl.exe --distribution Ubuntu --exec $driftopsNebiusExecutable --profile driftops @args
exit $LASTEXITCODE
