# B 端：group2 SSH 隧道 + health 验收 + 写入内网 API 设置
# 用法：powershell -ExecutionPolicy Bypass -File scripts\b_intranet_setup_group2.ps1

$ErrorActionPreference = "Stop"
$HostIP = "10.246.2.7"
$SshPort = 12202
$SshUser = "student"
$LocalPort = 8010
$BaseUrl = "http://127.0.0.1:$LocalPort"
$DemoKey = "hajimi-demo-2026"

Write-Host "[HAJIMI] 检查是否已有 SSH 隧道 (localhost:$LocalPort)..."
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/api/demo/health" -TimeoutSec 3
    Write-Host "[HAJIMI] 隧道/A 端已可达: $($health | ConvertTo-Json -Compress)"
} catch {
    Write-Host "[HAJIMI] 本地 health 不可达，请在新终端执行并保持窗口打开："
    Write-Host "  ssh -L ${LocalPort}:127.0.0.1:${LocalPort} ${SshUser}@${HostIP} -p ${SshPort}"
    Write-Host "  (密码见 校园gpu使用.md)"
    Write-Host ""
    Write-Host "若已建立隧道仍失败，请确认 A 端在容器内已启动 (scripts/gpu_group2_container_services.sh status)"
    exit 1
}

# 写入 user_settings.json
$settingsDir = Join-Path $env:LOCALAPPDATA "HAJIMI"
$settingsPath = Join-Path $settingsDir "user_settings.json"
New-Item -ItemType Directory -Force -Path $settingsDir | Out-Null
$settings = @{
    deployment_mode = "intranet"
    a_end_url         = $BaseUrl
    demo_key          = $DemoKey
    llm               = @{
        base_url = "https://api.deepseek.com"
        api_key  = ""
        model    = "deepseek-chat"
    }
    omniparser        = @{
        url     = "http://127.0.0.1:8002"
        gpu_url = ""
    }
}
$settings | ConvertTo-Json -Depth 4 | Set-Content -Path $settingsPath -Encoding UTF8
Write-Host "[HAJIMI] 已写入 $settingsPath (内网 API / $BaseUrl)"

Write-Host ""
Write-Host "=== health 详情 ==="
$health | Format-List

if ($health.status -ne "ok") {
    Write-Host "[FAIL] status 非 ok"
    exit 1
}
if ($health.omniparser_ready -eq $false) {
    Write-Host "[WARN] omniparser_ready=false，请联系 A 端重启 OmniParser"
}
Write-Host "[OK] B 端可启动 python main.py，系统设置应已为「内网 API」"
Write-Host "     网络方案: B (SSH 隧道) | Base URL: $BaseUrl"
