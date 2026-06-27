# mcp-finance 一键发布脚本
# 用法: .\release.ps1 "v0.12.10" "commit message"

param(
    [Parameter(Mandatory=$true)] [string]$Version,
    [Parameter(Mandatory=$true)] [string]$Message
)

$ver = $Version -replace '^v', ''
$ErrorActionPreference = "Stop"

Write-Host "🚀 Releasing $ver ..." -ForegroundColor Cyan

# 1. 更新版本号
$initFile = "mcp_finance\__init__.py"
(Get-Content $initFile -Raw) -replace '__version__ = "[\d.]+"', "__version__ = `"$ver`"" | Set-Content $initFile -NoNewline

$tomlFile = "pyproject.toml"
(Get-Content $tomlFile -Raw) -replace 'version = "[\d.]+"', "version = `"$ver`"" | Set-Content $tomlFile -NoNewline

# 2. 提交 + 打 tag
git add -A
git commit -m "$Message"
git tag -a "v$ver" -m "v$ver: $Message"
git push origin main --tags

# 3. 构建 + 发布
python -m build --wheel --no-isolation
python -m twine upload --repository pypi "dist/mcp_markets-$ver-py3-none-any.whl" --non-interactive

Write-Host "✅ v$ver published!" -ForegroundColor Green
