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

# 方法1：升级pip和setuptools
Write-Host "步骤 1/4: 升级pip、setuptools和wheel" -ForegroundColor Blue
python -m pip install --upgrade pip setuptools wheel

# 确保 setuptools 兼容性
Write-Host "步骤 1.5/4: 确保 setuptools 兼容性" -ForegroundColor Blue
try {
    python -c "from setuptools import setup" 2>$null
} catch {
    Write-Host "⚠ setuptools 版本可能不兼容，尝试重新安装" -ForegroundColor Yellow
    python -m pip install --force-reinstall setuptools
}

# 方法2：从requirements.txt安装依赖
Write-Host "步骤 2/4: 从requirements.txt安装依赖" -ForegroundColor Blue
Write-Host "安装依赖（版本号来自requirements.txt）..."

# 先安装数据处理依赖（使用预编译版本，避免构建错误）
Write-Host "步骤 2.1: 安装数据处理依赖..."
$depsResult = python -m pip install numpy pandas --prefer-binary
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ 数据处理依赖安装成功" -ForegroundColor Green
} else {
    Write-Host "⚠ 数据处理依赖安装失败，尝试备用方案..." -ForegroundColor Yellow
    python -m pip install numpy pandas
}

# 执行安装并捕获错误
$installResult = python -m pip install -r requirements.txt --prefer-binary
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ 核心依赖安装成功" -ForegroundColor Green
    $installStatus = 0
} else {
    Write-Host "✗ 核心依赖安装失败" -ForegroundColor Red
    Write-Host "尝试使用备用方案..." -ForegroundColor Yellow
    
    # 备用方案：不使用 --prefer-binary
    Write-Host "尝试不使用 --prefer-binary 选项..."
    $installResult = python -m pip install -r requirements.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ 备用方案安装成功" -ForegroundColor Green
        $installStatus = 0
    } else {
        Write-Host "✗ 备用方案也失败了" -ForegroundColor Red
        $installStatus = 1
    }
}

# 方法2.5：安装OCR功能依赖（可选）
Write-Host ""
Write-Host "是否安装 OCR 功能依赖？" -ForegroundColor Blue
Write-Host "OCR 功能用于扫描版 PDF 和图片文档识别"
Write-Host "这会安装额外的依赖：paddlepaddle、paddleocr、pytesseract、pymupdf、opencv-python"
$installOcr = Read-Host "是否安装 OCR 依赖? (y/n)"

if ($installOcr -eq "y") {
    Write-Host "步骤 2.5/4: 安装 OCR 功能依赖（可选）" -ForegroundColor Blue
    Write-Host "安装 OCR 依赖..."
    
    # 注意：paddleocr 在 Python 3.13 上有兼容性问题
    # 我们使用 Tesseract OCR 作为主要 OCR 引擎
    Write-Host "⚠ PaddleOCR 在 Python 3.13 上有兼容性问题" -ForegroundColor Yellow
    Write-Host "安装 Tesseract OCR 相关依赖..."
    
    # 先安装数据处理依赖（如果有）
    $numpyCheck = python -c "import pandas" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "安装数据处理依赖..."
        python -m pip install numpy pandas --prefer-binary
    }
    
    # 安装 OCR 核心依赖（Python 3.13 兼容）
    $ocrResult = python -m pip install pytesseract==0.3.13 pymupdf>=1.25.0 opencv-python>=4.13.0
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ OCR 依赖安装完成（Tesseract OCR）" -ForegroundColor Green
    } else {
        Write-Host "✗ OCR 依赖安装失败" -ForegroundColor Red
        Write-Host "跳过 OCR 依赖安装，可以稍后手动安装" -ForegroundColor Yellow
        Write-Host "手动安装命令: pip install pytesseract==0.3.13 pymupdf>=1.25.0 opencv-python>=4.13.0"
    }
} else {
    Write-Host "⚠ 跳过 OCR 依赖安装" -ForegroundColor Yellow
    Write-Host "  提示: 如需使用 OCR 功能，可以运行: pip install pytesseract==0.3.13 pymupdf>=1.25.0 opencv-python==4.9.0.80"
    Write-Host "  注意: 当前使用 Python 3.13，PaddleOCR 有兼容性问题，建议使用 Tesseract OCR"
}

# 方法3：验证安装
Write-Host "步骤 3/4: 检查安装状态" -ForegroundColor Blue

# 检查核心安装状态
if ($installStatus -ne 0) {
    Write-Host "✗ 核心依赖安装失败，跳过验证步骤" -ForegroundColor Red
    Write-Host "请查看上述错误信息，并尝试以下解决方案：" -ForegroundColor Yellow
    Write-Host "1. 清理 pip 缓存: pip cache purge"
    Write-Host "2. 重新安装: pip install -r requirements.txt --no-cache-dir"
    Write-Host "3. 手动安装失败的包"
    Write-Host "4. 使用预编译包: pip install -r requirements.txt --prefer-binary"
    Write-Host ""
    Write-Host "安装未完成，请解决上述问题后重新运行安装脚本" -ForegroundColor Red
    exit 1
}

Write-Host "✓ 依赖安装成功，开始验证..." -ForegroundColor Green
Write-Host ""
Write-Host "步骤 4/4: 验证安装" -ForegroundColor Blue

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
    Write-Host "  在虚拟环境中运行: .\scripts\check_prereqs.ps1"
} else {
    Write-Host "  运行: .\scripts\check_prereqs.ps1"
}
Write-Host ""
Write-Host "快速开始命令："
Write-Host "  python src/query_interface.py --data .\data"
Write-Host "  python src/desktop_app.py --status"
Write-Host "  python src/desktop_app.py --warm-up"
Write-Host ""
Write-Host "如果验证失败，请尝试以下替代方案："
Write-Host "1. 使用 --no-cache-dir: pip install -r requirements.txt --no-cache-dir"
Write-Host "2. 使用 --prefer-binary: pip install -r requirements.txt --prefer-binary"
Write-Host "3. 创建新的虚拟环境重新开始"
Write-Host ""
Write-Host "注意: 版本号在 requirements.txt 中统一管理，如需升级请修改该文件"