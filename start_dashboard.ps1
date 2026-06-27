# mcp-finance Dashboard 启动脚本
# 用法: 双击运行 或 PowerShell 执行

$ErrorActionPreference = "SilentlyContinue"
$port = 8080

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  mcp-finance Web Dashboard" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 清理旧进程
Write-Host "[1/2] 清理旧进程..." -ForegroundColor Yellow

# 杀掉占用端口的进程
$pids = (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object State -eq Listen).OwningProcess
foreach ($pid in $pids | Select-Object -Unique) {
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Write-Host "  已终止 PID $pid (端口 $port)" -ForegroundColor Gray
}

# 杀掉残留的 python dashboard 进程（Flask / 旧 FastAPI）
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
    if ($cmd -match "dashboard\.(app|fastapi_server|server)") {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  已终止残留 dashboard 进程 PID $($_.Id)" -ForegroundColor Gray
    }
}

Start-Sleep -Seconds 1

# 2. 启动服务
Write-Host "[2/2] 启动 Flask 服务..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  访问地址: http://localhost:$port" -ForegroundColor Green
Write-Host "  按 Ctrl+C 停止" -ForegroundColor Gray
Write-Host ""

Set-Location "D:\new idea\Mcp\mcp-stock-cn"
python -m mcp_finance.dashboard.app

Read-Host "`n按 Enter 退出"
