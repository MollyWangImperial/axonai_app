$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$workerToken = $env:ANALYSIS_WORKER_TOKEN
$tunnelToken = $env:CLOUDFLARE_TUNNEL_TOKEN
$modelRoot = "E:\Rehyn_Video_Projects\stroke_mocap_to_motion_encoder"
$modelPython = Join-Path $modelRoot ".venv\Scripts\python.exe"
$mocoPython = "D:\anaconda3\Anaconda3\python.exe"

if (-not $workerToken) {
    throw "Set ANALYSIS_WORKER_TOKEN to the same secret configured on Render."
}
if (-not $tunnelToken) {
    throw "Set CLOUDFLARE_TUNNEL_TOKEN to the token from the Cloudflare named tunnel."
}
if (-not (Test-Path -LiteralPath $modelPython)) {
    throw "CUDA model Python was not found at $modelPython"
}
if (-not (Test-Path -LiteralPath $mocoPython)) {
    throw "OpenSim Python was not found at $mocoPython"
}
$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    throw "cloudflared is not installed. Run: winget install --id Cloudflare.cloudflared"
}
if (Get-NetTCPConnection -LocalPort 8003 -State Listen -ErrorAction SilentlyContinue) {
    throw "Port 8003 is already in use. Stop the existing analysis worker first."
}

& $modelPython -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
if ($LASTEXITCODE -ne 0) { throw "CUDA is unavailable in the Rehyn model environment." }
& $mocoPython -c "import opensim; print(opensim.GetVersion())"
if ($LASTEXITCODE -ne 0) { throw "OpenSim is unavailable in the Moco environment." }

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoProfile", "-Command",
    "`$env:ANALYSIS_WORKER_TOKEN='$workerToken'; `$env:REHYN_MODEL_ROOT='$modelRoot'; `$env:REHYN_MOCO_PYTHON='$mocoPython'; & '$modelPython' '$PSScriptRoot\backend\local_gpu_worker.py'"
)

$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8003/health" -TimeoutSec 2
        if ($health.cuda.status -eq "ready" -and $health.musculoskeletal.configured) {
            $ready = $true
            break
        }
    } catch {}
}
if (-not $ready) { throw "The local analysis worker did not become ready within 60 seconds." }

Start-Process -FilePath $cloudflared.Source -WindowStyle Hidden -ArgumentList @(
    "tunnel", "--no-autoupdate", "run", "--token", $tunnelToken
)
Write-Host "Rehyn analysis worker is ready on the local RTX GPU and OpenSim/Moco runtime." -ForegroundColor Green
Write-Host "The authenticated Cloudflare tunnel is starting. Keep this computer awake during analysis." -ForegroundColor Green
