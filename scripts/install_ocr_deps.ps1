################################################################################
# OCR 功能依赖安装脚本 (Windows PowerShell 版本)
# 用于安装 OCR 图像识别功能所需的依赖
################################################################################

Write-Host "=== OCR 功能依赖安装脚本 ===" -ForegroundColor Blue
Write-Host "注意：OCR 功能是可选的，用于扫描版PDF和图片文档识别" -ForegroundColor Yellow
Write-Host ""

# 检查虚拟环境
if (-not $env:VIRTUAL_ENV) {
    Write-Host "⚠ 未检测到虚拟环境" -ForegroundColor Yellow
    Write-Host "建议使用虚拟环境来安装OCR依赖"
    $continueInstall = Read-Host "是否继续安装? (y/n)"
    if ($continueInstall -ne "y") {
        Write-Host "安装已取消"
        exit 0
    }
}

Write-Host ""
Write-Host "=== 步骤 1/4: 安装 Python OCR 包 ===" -ForegroundColor Blue
Write-Host "安装 OCR Python 依赖..."
pip install paddlepaddle==2.5.2
pip install paddleocr==2.7.0.3
pip install pytesseract==0.3.10
pip install pymupdf==1.23.8
pip install opencv-python==4.8.1.78
pip install pillow==10.1.0

Write-Host ""
Write-Host "=== 步骤 2/4: 安装 Tesseract 系统依赖 ===" -ForegroundColor Blue
Write-Host "检测到 Windows 系统"
Write-Host "需要手动安装 Tesseract"
Write-Host "1. 下载 Tesseract 安装程序："
Write-Host "   https://github.com/UB-Mannheim/tesseract/wiki"
Write-Host ""
Write-Host "2. 运行安装程序后，需要设置环境变量或配置路径"
Write-Host ""
Write-Host "3. 安装中文语言包（可选）"
Write-Host "   将语言包文件复制到 Tesseract 安装目录的 tessdata 文件夹"
Write-Host ""
Write-Host "下载地址："
Write-Host "   https://github.com/tesseract-ocr/tessdata/raw/main/chi_sim.traineddata"
Write-Host "   https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata"

$installTesseract = Read-Host "是否已安装 Tesseract? (y/n)"
if ($installTesseract -eq "y") {
    Write-Host "已安装 Tesseract" -ForegroundColor Green
} else {
    Write-Host "请先安装 Tesseract，然后运行此脚本完成剩余步骤" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 步骤 3/4: 验证 Python OCR 包安装 ===" -ForegroundColor Blue

function Test-Module {
    param([string]$Name, [string]$DisplayName)
    
    try {
        python -c "import $Name" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ $DisplayName" -ForegroundColor Green
            return $true
        } else {
            Write-Host "✗ $DisplayName" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "✗ $DisplayName" -ForegroundColor Red
        return $false
    }
}

Test-Module "paddleocr" "paddleocr"
Test-Module "pytesseract" "pytesseract"
Test-Module "fitz" "pymupdf"
Test-Module "cv2" "opencv-python"

Write-Host ""
Write-Host "=== 步骤 4/4: 验证 Tesseract 安装 ===" -ForegroundColor Blue

if (Get-Command tesseract -ErrorAction SilentlyContinue) {
    $tesseractVersion = tesseract --version 2>&1 | Select-Object -First 1
    Write-Host "✓ Tesseract 已安装: $tesseractVersion" -ForegroundColor Green
    
    Write-Host "已安装的语言包:"
    tesseract --list-langs 2>&1 | Select-Object -First 10
} else {
    Write-Host "⚠ Tesseract 未安装或未添加到PATH" -ForegroundColor Yellow
    Write-Host "请确保 Tesseract 已安装并添加到系统PATH"
}

Write-Host ""
Write-Host "=== OCR 依赖安装完成 ===" -ForegroundColor Blue
Write-Host ""
Write-Host "验证安装："
Write-Host "  运行: .\check_prereqs.ps1"
Write-Host ""
Write-Host "OCR 功能配置："
Write-Host "  在 config.py 中设置 OCR_ENABLED = True"
Write-Host "  选择 OCR 引擎: OCR_ENGINE = 'paddle' 或 'tesseract'"
Write-Host "  配置 Tesseract 路径: TESSERACT_PATH = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'"
Write-Host ""
Write-Host "使用示例："
Write-Host "  python query_interface.py --data .\scanned_docs"
Write-Host ""
Write-Host "注意：OCR 功能是可选的，如果不安装这些依赖，"
Write-Host "      系统会自动禁用 OCR 功能，不影响其他功能的使用。"
