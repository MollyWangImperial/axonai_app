# AxonAI App 一键启动（后端 + Expo QR）— 在仓库根目录右键"使用 PowerShell 运行"
# 前提：手机与电脑连同一个 WiFi；手机装好 Expo Go。
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Use the dedicated CUDA environment that contains the trained motion models.
$modelRoot = "E:\Rehyn_Video_Projects\stroke_mocap_to_motion_encoder"
$modelPython = Join-Path $modelRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $modelPython)) {
    throw "CUDA model Python was not found at $modelPython"
}
$gpuCheck = & $modelPython -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
if ($LASTEXITCODE -ne 0) { throw "The Rehyn CUDA environment cannot access this computer's GPU." }
Write-Host "Local model GPU: $gpuCheck" -ForegroundColor Green
$workerToken = [Guid]::NewGuid().ToString("N")

$backendPython = "D:\anaconda3\Anaconda3\python.exe"
if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Backend Python was not found at $backendPython"
}
& $backendPython -c "import fastapi, motor, uvicorn, opensim"
if ($LASTEXITCODE -ne 0) { throw "The backend Python environment is missing FastAPI, Motor, Uvicorn, or OpenSim." }
foreach ($port in 8001, 8003) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Close the existing Rehyn local process and run this launcher again."
    }
}

# 1) 自动探测本机局域网 IP，写入前端 .env.local（手机经它访问后端）
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -match '^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)' -and $_.InterfaceAlias -notmatch 'WSL|vEthernet|Loopback' } |
    Select-Object -First 1).IPAddress
if (-not $ip) { $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^127\.' } | Select-Object -First 1).IPAddress }
Set-Content -Path "frontend/.env.local" -Value "EXPO_PUBLIC_BACKEND_URL=http://$($ip):8001" -Encoding ascii
Write-Host "前端后端地址已设为 http://$($ip):8001" -ForegroundColor Green

# 2) Start the loopback-only CUDA worker. It preloads WHAM and the trained
# functional encoder; OpenSim/Moco continues on CPU behind its quality gate.
Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoProfile", "-Command",
    "`$env:ANALYSIS_WORKER_TOKEN='$workerToken'; `$env:REHYN_MODEL_ROOT='$modelRoot'; & '$modelPython' '$PSScriptRoot\backend\local_gpu_worker.py'"
)
Write-Host "CUDA worker starting on http://127.0.0.1:8003" -ForegroundColor Green
$gpuReady = $false
for ($attempt = 0; $attempt -lt 45; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8003/health" -TimeoutSec 2
        if ($health.cuda.status -eq "ready" -and $health.cuda.cuda -and $health.musculoskeletal.configured) {
            $gpuReady = $true
            break
        }
    } catch {}
}
if (-not $gpuReady) { throw "The local CUDA worker did not become ready within 45 seconds." }
Write-Host "CUDA models ready on $($health.cuda.gpu_name); OpenSim/Moco runtime ready" -ForegroundColor Green

# 3) 新窗口启动后端（Mongo 不可达时自动用内存回退，无需装 Mongo）
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$PSScriptRoot\backend'; `$env:MONGO_URL='mongodb://127.0.0.1:27017'; `$env:DB_NAME='axonai'; `$env:ANALYSIS_WORKER_TOKEN='$workerToken'; `$env:LOCAL_GPU_WORKER_URL='http://127.0.0.1:8003'; `$env:LOCAL_BACKEND_CALLBACK_URL='http://127.0.0.1:8001/api'; & '$backendPython' -m uvicorn server:app --host 0.0.0.0 --port 8001"
)
Write-Host "后端窗口已启动 (端口 8001)" -ForegroundColor Green

# 4) 本窗口启动 Expo —— 终端会显示二维码，用手机 Expo Go 扫码
Set-Location "$PSScriptRoot\frontend"
npx expo start
