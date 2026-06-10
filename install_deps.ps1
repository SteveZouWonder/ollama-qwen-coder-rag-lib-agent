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

# 方法1：升级pip
Write-Host "步骤 1/4: 升级pip和setuptools" -ForegroundColor Blue
python -m pip install --upgrade pip setuptools wheel

# 方法2：分步安装核心依赖
Write-Host "步骤 2/4: 分步安装核心依赖" -ForegroundColor Blue

# 先安装banks（导致问题的包）
Write-Host "安装banks..."
python -m pip install banks==2.4.0

# 然后安装其他核心依赖
Write-Host "安装chromadb..."
python -m pip install chromadb==0.4.24

Write-Host "安装pypdf..."
python -m pip install pypdf==4.3.1

Write-Host "安装requests..."
python -m pip install requests==2.32.3

Write-Host "安装python-dotenv..."
python -m pip install python-dotenv==1.0.1

Write-Host "安装rich..."
python -m pip install rich==13.9.4

Write-Host "安装prompt-toolkit..."
python -m pip install prompt-toolkit==3.0.48

# 方法3：安装llama-index相关依赖
Write-Host "步骤 3/4: 安装llama-index相关依赖" -ForegroundColor Blue

# 先安装llama-index核心
Write-Host "安装llama-index核心..."
python -m pip install llama-index==0.10.46

# 然后安装各个扩展包
Write-Host "安装llama-index扩展包..."
python -m pip install llama-index-embeddings-ollama==0.1.3
python -m pip install llama-index-llms-ollama==0.2.0
python -m pip install llama-index-readers-file==0.1.4
python -m pip install llama-index-vector-stores-chroma==0.1.8

# 方法4：验证安装
Write-Host "步骤 4/4: 验证安装" -ForegroundColor Blue

Write-Host "验证关键依赖..."

$deps = @("llama_index", "chromadb", "pypdf", "rich", "prompt_toolkit")
foreach ($dep in $deps) {
    try {
        python -c "import $dep" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ $dep" -ForegroundColor Green
        } else {
            Write-Host "✗ $dep" -ForegroundColor Red
        }
    } catch {
        Write-Host "✗ $dep" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Blue
Write-Host ""
Write-Host "如果还有问题，请尝试以下替代方案："
Write-Host "1. 使用 --no-cache-dir: pip install -r requirements.txt --no-cache-dir"
Write-Host "2. 使用 --prefer-binary: pip install -r requirements.txt --prefer-binary"
Write-Host "3. 创建新的虚拟环境重新开始"