################################################################################
# 前置条件检查脚本 (Windows PowerShell 版本)
# 用于验证智能文档+代码助手项目所需的所有前置条件
################################################################################

# 统计变量
$TOTAL_CHECKS = 0
$PASSED_CHECKS = 0
$FAILED_CHECKS = 0
$WARNING_CHECKS = 0

# 问题分类统计
$PYTHON_ISSUES = 0
$OLLAMA_ISSUES = 0
$DEPENDENCY_ISSUES = 0
$NETWORK_ISSUES = 0

# 打印标题函数
function Print-Header {
    param([string]$Title)
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Blue
    Write-Host "$Title" -ForegroundColor Blue
    Write-Host "========================================" -ForegroundColor Blue
}

# 打印检查结果函数
function Print-Result {
    param([int]$Status, [string]$Message)
    
    $script:TOTAL_CHECKS++
    
    switch ($Status) {
        0 {
            Write-Host "✓ $Message" -ForegroundColor Green
            $script:PASSED_CHECKS++
        }
        1 {
            Write-Host "✗ $Message" -ForegroundColor Red
            $script:FAILED_CHECKS++
        }
        2 {
            Write-Host "⚠ $Message" -ForegroundColor Yellow
            $script:WARNING_CHECKS++
        }
    }
}

# 检查命令是否存在
function Test-Command {
    param([string]$Command)
    try {
        $null = Get-Command $Command -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# 检查Python版本
function Test-PythonVersion {
    if (Test-Command python) {
        try {
            $version = python --version 2>&1
            $versionNumber = $version -replace 'Python ', ''
            $major, $minor = $versionNumber.Split('.')[0..1]
            
            if ([int]$major -gt 3 -or ([int]$major -eq 3 -and [int]$minor -ge 8)) {
                Print-Result 0 "Python 版本: $version"
                return $true
            } else {
                Print-Result 1 "Python 版本过低: $version (需要 3.8+)"
                return $false
            }
        } catch {
            Print-Result 1 "Python 不可用"
            return $false
        }
    } else {
        Print-Result 1 "Python 未安装"
        return $false
    }
}

# 检查pip
function Test-Pip {
    if (Test-Command pip) {
        try {
            $version = pip --version 2>&1
            Print-Result 0 "pip 版本: $version"
            return $true
        } catch {
            Print-Result 1 "pip 不可用"
            return $false
        }
    } else {
        Print-Result 1 "pip 未安装"
        return $false
    }
}

# 检查Ollama
function Test-Ollama {
    if (Test-Command ollama) {
        Print-Result 0 "Ollama 已安装"
        
        # 检查版本
        $version = ollama --version 2>&1
        Write-Host "  版本: $version"
        
        # 检查服务状态
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            Print-Result 0 "Ollama 服务运行中 (端口 11434)"
        } catch {
            Print-Result 1 "Ollama 服务未运行"
            Write-Host "  请运行: ollama serve"
        }
        
        # 检查模型
        Write-Host "  已安装的模型:"
        $models = ollama list 2>&1
        if ($models -match "qwen2.5-coder") {
            Print-Result 0 "qwen2.5-coder 模型已安装"
        } else {
            Print-Result 1 "qwen2.5-coder 模型未安装"
            Write-Host "  请运行: ollama pull qwen2.5-coder:7b"
        }
        
        if ($models -match "nomic-embed-text") {
            Print-Result 0 "nomic-embed-text 模型已安装"
        } else {
            Print-Result 1 "nomic-embed-text 模型未安装"
            Write-Host "  请运行: ollama pull nomic-embed-text:latest"
        }
        
        return $true
    } else {
        Print-Result 1 "Ollama 未安装"
        Write-Host "  请访问: https://ollama.com/download"
        return $false
    }
}

# 检查Git
function Test-Git {
    if (Test-Command git) {
        $version = git --version 2>&1
        Print-Result 0 "Git 版本: $version"
        return $true
    } else {
        Print-Result 2 "Git 未安装 (可选)"
        return $false
    }
}

# 检查curl
function Test-Curl {
    if (Test-Command curl) {
        $version = curl --version 2>&1 | Select-Object -First 1
        Print-Result 0 "curl 已安装: $version"
        return $true
    } else {
        Print-Result 1 "curl 未安装"
        return $false
    }
}

# 检查系统内存
function Test-Memory {
    $os = Get-CimInstance -ClassName Win32_ComputerSystem
    $totalMemory = [math]::Round($os.TotalPhysicalMemory / 1GB, 2)
    $freeMemory = [math]::Round((Get-CimInstance -ClassName Win32_OperatingSystem).FreePhysicalMemory / 1GB, 2)
    
    if ($totalMemory -gt 8) {
        Print-Result 0 "系统内存: ${totalMemory}GB (可用: ${freeMemory}GB)"
    } else {
        Print-Result 1 "系统内存不足: ${totalMemory}GB (建议 > 8GB)"
    }
}

# 检查磁盘空间
function Test-DiskSpace {
    $drive = Get-PSDrive -Name C
    $freeSpace = [math]::Round($drive.Free / 1GB, 2)
    
    if ($freeSpace -gt 10) {
        Print-Result 0 "磁盘空间: ${freeSpace}GB 可用"
    } else {
        Print-Result 1 "磁盘空间不足: ${freeSpace}GB 可用 (需要 > 10GB)"
    }
}

# 检查Python依赖
function Test-Dependencies {
    if (-not (Test-Path "requirements.txt")) {
        Print-Result 1 "requirements.txt 文件不存在"
        return $false
    }
    
    # 检查虚拟环境
    if ($env:VIRTUAL_ENV) {
        Print-Result 0 "虚拟环境已激活: $env:VIRTUAL_ENV"
        $PYTHON_CMD = "python"
        $PIP_CMD = "pip"
    } else {
        Print-Result 2 "未检测到虚拟环境 (推荐使用)"
        $PYTHON_CMD = "python3"
        $PIP_CMD = "pip3"
        Write-Host "  提示: 使用虚拟环境可以避免依赖冲突"
        Write-Host "  创建方法: python -m venv venv; .\venv\Scripts\Activate"
    }
    
    # 检查pip命令
    if (Get-Command pip -ErrorAction SilentlyContinue) {
        $PIP_CMD = "pip"
    } elseif (Get-Command pip3 -ErrorAction SilentlyContinue) {
        $PIP_CMD = "pip3"
    } else {
        Print-Result 1 "pip未安装"
        Write-Host "  请运行: $PYTHON_CMD -m ensurepip --upgrade"
        return $false
    }
    
    # 尝试导入关键模块并获取详细错误信息
    $dep_failures = 0
    
    $modules = @(
        @{name="llama_index"; display="llama-index"},
        @{name="chromadb"; display="chromadb"},
        @{name="rich"; display="rich"},
        @{name="prompt_toolkit"; display="prompt-toolkit"},
        @{name="pypdf"; display="pypdf"},
        @{name="requests"; display="requests"},
        @{name="dotenv"; display="python-dotenv"},
        @{name="urllib3"; display="urllib3"}
    )
    
    foreach ($module in $modules) {
        try {
            $output = python -c "import $($module.name)" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Print-Result 0 "$($module.display) 已安装"
            } else {
                Print-Result 1 "$($module.display) 未安装"
                
                # 根据错误信息提供针对性建议
                if ($output -match "ModuleNotFoundError") {
                    Write-Host "  错误: 模块未找到"
                    Write-Host "  解决方案: $PIP_CMD install $($module.name)"
                } elseif ($output -match "ImportError") {
                    Write-Host "  错误: 依赖导入失败"
                    Write-Host "  解决方案: $PIP_CMD install --upgrade $($module.name)"
                } elseif ($output -match "Permission denied") {
                    Write-Host "  错误: 权限不足"
                    Write-Host "  解决方案: 使用虚拟环境或以管理员身份运行"
                } else {
                    Write-Host "  错误: $output"
                    Write-Host "  解决方案: $PIP_CMD install -r requirements.txt"
                }
                $dep_failures++
            }
        } catch {
            Print-Result 1 "$($module.display) 未安装"
            Write-Host "  错误: $($_.Exception.Message)"
            Write-Host "  解决方案: $PIP_CMD install -r requirements.txt"
            $dep_failures++
        }
    }
    
    if ($dep_failures -gt 0) {
        $script:DEPENDENCY_ISSUES += $dep_failures
        Write-Host ""
        Write-Host "  提示: 运行 .\install_deps.ps1 自动解决依赖问题"
    }
    
    # 检查urllib3 SSL兼容性
    try {
        $sslVersion = python -c "import ssl; print(ssl.OPENSSL_VERSION)" 2>$null
        $urllib3Version = python -c "import urllib3; print(urllib3.__version__)" 2>$null
        Write-Host "urllib3 版本: $urllib3Version"
        if ($sslVersion -like "*LibreSSL*" -and $urllib3Version -like "2.*") {
            Print-Result 1 "urllib3 2.x 与 LibreSSL 不兼容"
            Write-Host "  建议: 使用Homebrew Python或降级urllib3"
        } else {
            Print-Result 0 "urllib3 SSL 兼容性正常"
        }
    } catch {
        # 忽略错误
    }
    
    # 检查桌面应用依赖（必需）
    Write-Host "检查桌面应用依赖..."
    $desktopDeps = @(
        @{name="pystray"; display="pystray"; hint="pip install pystray"},
        @{name="PIL"; display="PIL/pillow"; hint="pip install pillow"}
    )
    foreach ($dep in $desktopDeps) {
        try {
            python -c "import $($dep.name)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Print-Result 0 "$($dep.display) 已安装"
            } else {
                Print-Result 1 "$($dep.display) 未安装 (桌面应用必需)"
                Write-Host "  解决方案: $($dep.hint)"
                $dep_failures++
            }
        } catch {
            Print-Result 1 "$($dep.display) 未安装 (桌面应用必需)"
            Write-Host "  解决方案: $($dep.hint)"
            $dep_failures++
        }
    }
    
    # 检查测试工具（可选）
    Write-Host "检查测试工具（可选）..."
    $testDeps = @(
        @{name="pytest"; display="pytest"; hint="pip install pytest 用于运行测试"},
        @{name="pytest_cov"; display="pytest-cov"; hint="pip install pytest-cov 用于测试覆盖率"}
    )
    foreach ($dep in $testDeps) {
        try {
            python -c "import $($dep.name)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Print-Result 0 "$($dep.display) 已安装 (测试工具)"
            } else {
                Print-Result 2 "$($dep.display) 未安装 (测试工具可选)"
                Write-Host "  提示: $($dep.hint)"
            }
        } catch {
            Print-Result 2 "$($dep.display) 未安装 (测试工具可选)"
            Write-Host "  提示: $($dep.hint)"
        }
    }
}

# 检查项目文件
function Test-ProjectFiles {
    $requiredFiles = @(
        "config.py",
        "query_interface.py",
        "rag_engine.py",
        "react_engine.py",
        "agent_tools.py",
        "document_loader.py",
        "desktop_app.py",
        "knowledge_snapshot.py",
        "knowledge_to_skills.py",
        "content_security.py",
        "chat_history.py"
    )
    
    $missingFiles = 0
    foreach ($file in $requiredFiles) {
        if (Test-Path $file) {
            # 文件存在
        } else {
            Write-Host "✗ 缺少文件: $file" -ForegroundColor Red
            $missingFiles++
        }
    }
    
    if ($missingFiles -eq 0) {
        Print-Result 0 "所有项目文件完整"
    } else {
        Print-Result 1 "缺少 $missingFiles 个项目文件"
    }
}

# 检查网络连接
function Test-Network {
    $network_issues = 0
    try {
        $response = Invoke-WebRequest -Uri "https://www.google.com" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Print-Result 0 "网络连接正常"
    } catch {
        Print-Result 1 "网络连接异常"
        Write-Host "  请检查网络设置或代理配置"
        $network_issues++
    }
    
    # 检查Ollama API
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Print-Result 0 "Ollama API 可访问"
    } catch {
        Print-Result 1 "Ollama API 不可访问"
        Write-Host "  请确保 Ollama 服务正在运行"
        $network_issues++
    }
    
    if ($network_issues -gt 0) {
        $script:NETWORK_ISSUES += $network_issues
    }
}

# 主函数
function Main {
    Print-Header "前置条件检查开始"
    
    # 基础命令检查
    Print-Header "基础命令检查"
    Test-PythonVersion
    Test-Pip
    Test-Git
    Test-Curl
    
    # 系统资源检查
    Print-Header "系统资源检查"
    Test-Memory
    Test-DiskSpace
    
    # Ollama检查
    Print-Header "Ollama 检查"
    Test-Ollama
    
    # Python依赖检查
    Print-Header "Python 依赖检查"
    Test-Dependencies
    
    # 项目文件检查
    Print-Header "项目文件检查"
    Test-ProjectFiles
    
    # 网络检查
    Print-Header "网络检查"
    Test-Network
    
    # 总结
    Print-Header "检查总结"
    Write-Host "总检查项: $TOTAL_CHECKS"
    Write-Host "通过: $PASSED_CHECKS" -ForegroundColor Green
    Write-Host "失败: $FAILED_CHECKS" -ForegroundColor Red
    Write-Host "警告: $WARNING_CHECKS" -ForegroundColor Yellow
    
    if ($FAILED_CHECKS -eq 0) {
        Write-Host ""
        Write-Host "✓ 所有必要条件已满足，可以开始使用！" -ForegroundColor Green
        Write-Host ""
        Write-Host "快速开始命令："
        Write-Host "  python desktop_app.py              # 启动桌面应用（推荐）"
        Write-Host "  python desktop_app.py --status     # 检查服务状态"
        Write-Host "  python desktop_app.py --warm-up    # 预热模型"
        Write-Host "  python query_interface.py --data .\data  # 命令行模式"
        return 0
    } else {
        Write-Host ""
        Write-Host "✗ 发现 $FAILED_CHECKS 个问题，请按以下顺序解决：" -ForegroundColor Red
        Write-Host ""
        
        # 根据问题类型提供针对性建议
        if ($PYTHON_ISSUES -gt 0) {
            Write-Host "Python相关问题 ($PYTHON_ISSUES 个):" -ForegroundColor Yellow
            Write-Host "  1. 安装或升级Python: 从 https://www.python.org/downloads/ 下载"
            Write-Host "  2. 验证版本: python --version"
            Write-Host ""
        }
        
        if ($OLLAMA_ISSUES -gt 0) {
            Write-Host "Ollama相关问题 ($OLLAMA_ISSUES 个):" -ForegroundColor Yellow
            Write-Host "  1. 安装Ollama: 从 https://ollama.com/download 下载"
            Write-Host "  2. 启动服务: ollama serve"
            Write-Host "  3. 下载模型: ollama pull qwen2.5-coder:7b"
            Write-Host "  4. 验证服务: curl http://localhost:11434/api/tags"
            Write-Host ""
        }
        
        if ($DEPENDENCY_ISSUES -gt 0) {
            Write-Host "Python依赖相关问题 ($DEPENDENCY_ISSUES 个):" -ForegroundColor Yellow
            Write-Host "  1. 自动安装: .\install_deps.ps1  # 推荐"
            Write-Host "  2. 手动安装: pip install -r requirements.txt"
            Write-Host "  3. 或使用备用配置: pip install -r requirements_alternative.txt"
            Write-Host "  4. 检查虚拟环境: 确保在虚拟环境中运行"
            Write-Host ""
        }
        
        if ($NETWORK_ISSUES -gt 0) {
            Write-Host "网络相关问题 ($NETWORK_ISSUES 个):" -ForegroundColor Yellow
            Write-Host "  1. 检查网络连接: Test-Connection google.com"
            Write-Host "  2. 检查防火墙设置"
            Write-Host "  3. 配置代理（如果需要）"
            Write-Host "  4. 重启Ollama服务: ollama serve"
            Write-Host ""
        }
        
        Write-Host "解决所有问题后，重新运行此脚本验证："
        Write-Host "  .\check_prereqs.ps1"
        
        return 1
    }
}

# 运行主函数
Main