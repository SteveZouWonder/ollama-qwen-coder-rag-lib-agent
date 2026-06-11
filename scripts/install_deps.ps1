################################################################################
# 依赖安装脚本 (Windows PowerShell 版本)
# 解决依赖冲突问题
################################################################################

Write-Host "=== 依赖安装脚本 ===" -ForegroundColor Blue

# 检查虚拟环境
if (-not $env:VIRTUAL_ENV) {
    Write-Host "⚠ 未检测到虚拟环境，建议使用虚拟环境" -ForegroundColor Yellow
    $create_venv = Read-Host "是否创建虚拟环境? (y/n)"
    if ($create_venv -eq "y") {
        python -m venv venv
        .\venv\Scripts\Activate.ps1
        Write-Host "✓ 虚拟环境已激活" -ForegroundColor Green
    }
} else {
    Write-Host "✓ 虚拟环境已激活: $env:VIRTUAL_ENV" -ForegroundColor Green
}

# 检查requirements.txt文件
if (-not (Test-Path "requirements.txt")) {
    Write-Host "✗ requirements.txt 文件不存在" -ForegroundColor Red
    exit 1
}

# 方法1：升级pip
Write-Host "步骤 1/3: 升级pip和setuptools" -ForegroundColor Blue
python -m pip install --upgrade pip setuptools wheel

# 方法2：从requirements.txt安装依赖
Write-Host "步骤 2/3: 从requirements.txt安装依赖" -ForegroundColor Blue
Write-Host "安装依赖（版本号来自requirements.txt）..."
python -m pip install -r requirements.txt

# 方法3：验证安装
Write-Host "步骤 3/3: 验证安装" -ForegroundColor Blue

Write-Host "验证核心依赖..."

$deps = @(
    @{name="llama_index"; display="llama-index"},
    @{name="chromadb"; display="chromadb"},
    @{name="pypdf"; display="pypdf"},
    @{name="rich"; display="rich"},
    @{name="prompt_toolkit"; display="prompt-toolkit"},
    @{name="requests"; display="requests"},
    @{name="dotenv"; display="python-dotenv"},
    @{name="urllib3"; display="urllib3"}
)

foreach ($dep in $deps) {
    try {
        python -c "import $($dep.name)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ $($dep.display)" -ForegroundColor Green
        } else {
            Write-Host "✗ $($dep.display)" -ForegroundColor Red
        }
    } catch {
        Write-Host "✗ $($dep.display)" -ForegroundColor Red
    }
}

# 检查urllib3 SSL兼容性
Write-Host "检查urllib3 SSL兼容性..."
try {
    $sslVersion = python -c "import ssl; print(ssl.OPENSSL_VERSION)" 2>$null
    $urllib3Version = python -c "import urllib3; print(urllib3.__version__)" 2>$null
    if ($sslVersion -like "*LibreSSL*" -and $urllib3Version -like "2.*") {
        Write-Host "⚠ urllib3 2.x 与 LibreSSL 不兼容" -ForegroundColor Yellow
    }
} catch {
    # 忽略错误
}

Write-Host ""
Write-Host "验证测试工具（可选）..."
$testDeps = @("pytest", "pytest_cov")
foreach ($dep in $testDeps) {
    try {
        python -c "import $dep" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ $dep" -ForegroundColor Green
        } else {
            Write-Host "⚠ $dep 未安装（测试工具可选）" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "⚠ $dep 未安装（测试工具可选）" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Blue
Write-Host ""
Write-Host "验证安装："
if ($env:VIRTUAL_ENV) {
    Write-Host "  在虚拟环境中运行: .\check_prereqs.ps1"
} else {
    Write-Host "  运行: .\check_prereqs.ps1"
}
Write-Host ""
Write-Host "快速开始命令："
Write-Host "  python query_interface.py --data .\data"
Write-Host "  python desktop_app.py --status"
Write-Host "  python desktop_app.py --warm-up"
Write-Host ""
Write-Host "如果验证失败，请尝试以下替代方案："
Write-Host "1. 使用 --no-cache-dir: pip install -r requirements.txt --no-cache-dir"
Write-Host "2. 使用 --prefer-binary: pip install -r requirements.txt --prefer-binary"
Write-Host "3. 创建新的虚拟环境重新开始"
Write-Host ""
Write-Host "注意: 版本号在 requirements.txt 中统一管理，如需升级请修改该文件"