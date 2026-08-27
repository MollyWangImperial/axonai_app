# Rehyn local analysis worker

The hosted Render app can submit an assessment to this computer for CUDA and OpenSim/Moco processing through an authenticated Cloudflare Tunnel.

## One-time Cloudflare setup

1. Create a **named tunnel** in Cloudflare Zero Trust and map a private hostname such as `analysis.example.com` to `http://localhost:8003`.
2. Protect the hostname with a Cloudflare Access service application.
3. Create a service token for Render and retain its Client ID and Client Secret.
4. Copy the tunnel token for this computer.
5. Install the connector with `winget install --id Cloudflare.cloudflared`.

Do not use an unauthenticated quick tunnel for patient recordings.

## Render variables

Configure these on the `rehyn` Render service:

- `LOCAL_GPU_WORKER_URL=https://analysis.example.com`
- `LOCAL_BACKEND_CALLBACK_URL=https://rehyn.onrender.com/api`
- `ANALYSIS_WORKER_TOKEN=<one strong shared secret>`
- `ANALYSIS_WORKER_CF_CLIENT_ID=<Cloudflare Access service token ID>`
- `ANALYSIS_WORKER_CF_CLIENT_SECRET=<Cloudflare Access service token secret>`

The same `ANALYSIS_WORKER_TOKEN` must be present on this computer. Keep all values out of Git.

## Start the worker

In PowerShell:

```powershell
$env:ANALYSIS_WORKER_TOKEN = "<same strong shared secret as Render>"
$env:CLOUDFLARE_TUNNEL_TOKEN = "<named tunnel token>"
.\start_render_analysis_worker.ps1
```

The launcher checks the RTX CUDA runtime and OpenSim installation, starts the worker on loopback port 8003, then starts the named tunnel. The computer must stay powered on and connected while an assessment is processing.

## Optional direct video storage

Cloudflare R2 lets the browser upload task recordings without sending the video body through Render. Configure the following Render variables:

- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`

Allow `PUT` from `https://rehyn.onrender.com` in the R2 bucket CORS policy and allow the `Content-Type` header. Without R2, the app continues to use the existing backend upload route.

## Reporting boundary

The walking pipeline runs real OpenSim Moco optimization. Its current 2D generic gait model is not subject-scaled and does not use measured force plates, so its muscle-demand values are research estimates. They appear as patient insights but cannot unlock an automatic rehabilitation plan. Only the separate fully quality-validated model-result contract can do that.
