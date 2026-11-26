<#
程序说明：将打包好的 cp0-screen-cast_0.1.0_arm64.deb 通过 SSH 上传到 CardputerZero 并执行安装。
用法示例：
  powershell -ExecutionPolicy Bypass -File .\deploy_to_device.ps1 -Target "cardputer"
#>
param(
    [string]$Target = "cardputer",
    [string]$DebPath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $DebPath) {
    $DebPath = Join-Path $ScriptDir "dist\cp0-screen-cast_0.1.0_arm64.deb"
}

if (-not (Test-Path -LiteralPath $DebPath)) {
    Write-Host "未找到安装包，正在调用 build_deb.py 生成..."
    & python (Join-Path $ScriptDir "build_deb.py")
}

$FileName = Split-Path -Leaf $DebPath
Write-Host "正在上传 $FileName 到 ${Target}:~/ ..."
& scp "$DebPath" "${Target}:~/$FileName"
if ($LASTEXITCODE -ne 0) {
    throw "SCP 上传失败，请检查设备网络连接与 SSH 配置。"
}

Write-Host "正在设备端安装 $FileName ..."
& ssh "$Target" "sudo dpkg -i ~/$FileName"
if ($LASTEXITCODE -ne 0) {
    throw "dpkg 安装返回非零状态，请在设备端检查依赖（python3-pil / python3-numpy）。"
}

Write-Host "安装完成！可在设备桌面 APPLaunch 中打开 ScreenCast，或运行 cp0-screen-cast 启动。"
