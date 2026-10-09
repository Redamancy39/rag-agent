param(
    [ValidateSet('start', 'stop', 'check')]
    [string]$Action = 'start',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$venvDir = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$runtimeDir = Join-Path $backendDir '.runtime_logs\local-launcher'
$stateFile = Join-Path $runtimeDir 'state.json'
$backendUrl = 'http://127.0.0.1:8000'
$frontendUrl = 'http://127.0.0.1:5173'
$script:services = @{ backend = $null; frontend = $null }
$script:startedNow = New-Object System.Collections.ArrayList

function Read-LaunchState {
    if (-not (Test-Path -LiteralPath $stateFile)) { return }
    try {
        $saved = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        if (-not [string]::Equals($saved.project_root, $projectRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw '项目路径不一致。'
        }
        $script:services.backend = $saved.backend
        $script:services.frontend = $saved.frontend
    } catch {
        throw "启动状态文件无法验证，已保留：$stateFile。$($_.Exception.Message)"
    }
}

function Save-LaunchState {
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    $record = @{ project_root = $projectRoot; backend = $script:services.backend; frontend = $script:services.frontend }
    $json = $record | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText($stateFile, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-OwnedProcess([string]$Role) {
    $entry = $script:services[$Role]
    if ($null -eq $entry) { return $null }
    $candidate = Get-Process -Id ([int]$entry.process_id) -ErrorAction SilentlyContinue
    if ($null -eq $candidate) { return $null }
    try {
        $created = $candidate.StartTime
        if ($null -eq $created -or $candidate.HasExited) { return $null }
        if ($created.ToUniversalTime().Ticks -ne [long]$entry.start_ticks) { return $null }
    } catch { return $null }
    $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($candidate.Id)"
    if ($null -eq $details -or [string]::IsNullOrWhiteSpace($details.CommandLine)) { return $null }
    if ($Role -eq 'backend') {
        $entryPoint = Join-Path $projectRoot 'scripts\run-local-backend.py'
        if ($details.CommandLine.IndexOf($entryPoint, [StringComparison]::OrdinalIgnoreCase) -lt 0) { return $null }
        if (-not [string]::Equals($details.ExecutablePath, $venvPython, [StringComparison]::OrdinalIgnoreCase)) { return $null }
    } else {
        $entryPoint = Join-Path $frontendDir 'scripts\dev.mjs'
        if ($details.CommandLine.IndexOf($entryPoint, [StringComparison]::OrdinalIgnoreCase) -lt 0) { return $null }
    }
    return $candidate
}

function Stop-OwnedService([string]$Role) {
    $rootProcess = Get-OwnedProcess $Role
    if ($null -eq $rootProcess) {
        $script:services[$Role] = $null
        return
    }
    # Only descendants of a verified launcher-owned process are stopped.
    $snapshot = @(Get-CimInstance Win32_Process)
    $family = New-Object System.Collections.ArrayList
    [void]$family.Add([int]$rootProcess.Id)
    for ($index = 0; $index -lt $family.Count; $index++) {
        foreach ($child in $snapshot) {
            if ([int]$child.ParentProcessId -eq [int]$family[$index] -and -not $family.Contains([int]$child.ProcessId)) {
                [void]$family.Add([int]$child.ProcessId)
            }
        }
    }
    for ($index = $family.Count - 1; $index -ge 0; $index--) {
        $member = Get-Process -Id ([int]$family[$index]) -ErrorAction SilentlyContinue
        $original = $snapshot | Where-Object ProcessId -EQ ([int]$family[$index]) | Select-Object -First 1
        if ($null -eq $member -or $null -eq $original) { continue }
        try {
            $actualCreated = $member.StartTime
            $originalCreated = $original.CreationDate
            if ($null -eq $actualCreated -or $null -eq $originalCreated -or $member.HasExited) { continue }
            if ([Math]::Abs($actualCreated.ToUniversalTime().Ticks - $originalCreated.ToUniversalTime().Ticks) -lt [TimeSpan]::TicksPerMillisecond) {
                Stop-Process -Id $member.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {
            # Python's venv parent can exit immediately after its child exits.
            if (Get-Process -Id ([int]$family[$index]) -ErrorAction SilentlyContinue) { throw }
        }
    }
    if ($null -ne (Get-OwnedProcess $Role)) { throw "$Role 进程尚未停止，状态记录已保留。" }
    $script:services[$Role] = $null
}

function Test-PortOccupied([int]$Port) {
    return @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object Port -EQ $Port).Count -gt 0
}

function Test-Endpoint([string]$Role) {
    $response = $null
    $reader = $null
    try {
        $url = if ($Role -eq 'backend') { "$backendUrl/health" } else { "$frontendUrl/src/main.ts" }
        $request = [Net.HttpWebRequest]::Create($url)
        $request.Proxy = $null
        $request.Timeout = 2000
        $request.ReadWriteTimeout = 2000
        $response = $request.GetResponse()
        $reader = New-Object IO.StreamReader($response.GetResponseStream())
        $content = $reader.ReadToEnd()
        if ([int]$response.StatusCode -ne 200) { return $false }
        if ($Role -eq 'backend') { return ($content | ConvertFrom-Json).status -eq 'ok' }
        return $content -match 'createApp'
    } catch { return $false } finally {
        if ($null -ne $reader) { $reader.Dispose() }
        if ($null -ne $response) { $response.Dispose() }
    }
}

function Wait-Service([string]$Role) {
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        if ($null -eq (Get-OwnedProcess $Role)) { throw "$Role 启动进程已退出，请查看日志：$runtimeDir" }
        if (Test-Endpoint $Role) { return }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Role 未在 45 秒内就绪，请查看日志：$runtimeDir"
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "命令执行失败（退出码 $LASTEXITCODE）：$Executable" }
}

function Test-CommandQuietly([string]$Executable, [string[]]$Arguments) {
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Executable @Arguments *> $null
        return $LASTEXITCODE -eq 0
    } catch { return $false } finally { $ErrorActionPreference = $oldPreference }
}

function Test-Python([string]$Executable, [string[]]$Prefix) {
    try {
        & $Executable @Prefix -c 'import sys; sys.exit(0 if sys.version_info.major == 3 and 10 <= sys.version_info.minor <= 13 else 1)' 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Ensure-PythonEnvironment {
    if (Test-Path -LiteralPath $venvDir) {
        if (-not (Test-Path -LiteralPath $venvPython) -or -not (Test-Python $venvPython @())) {
            throw '现有 .venv 不可用，已保留。请先修复/移走该虚拟环境，再重试；不会自动覆盖。'
        }
    } else {
        $choices = New-Object System.Collections.ArrayList
        if ($env:RAG_PYTHON) { [void]$choices.Add(@{ executable = $env:RAG_PYTHON; prefix = @() }) }
        if (Get-Command py.exe -ErrorAction SilentlyContinue) {
            foreach ($version in @('-3.11', '-3.12', '-3.10', '-3.13')) {
                [void]$choices.Add(@{ executable = 'py.exe'; prefix = @($version) })
            }
        }
        if ($env:CONDA_PREFIX) { [void]$choices.Add(@{ executable = (Join-Path $env:CONDA_PREFIX 'python.exe'); prefix = @() }) }
        if (Get-Command python.exe -ErrorAction SilentlyContinue) { [void]$choices.Add(@{ executable = 'python.exe'; prefix = @() }) }
        $selected = $null
        foreach ($choice in $choices) {
            if (Test-Python $choice.executable $choice.prefix) { $selected = $choice; break }
        }
        if ($null -eq $selected) { throw '未找到 Python 3.10–3.13。请安装 Python 3.11，或将 RAG_PYTHON 设为可用的 python.exe 路径。' }
        Write-Host '[1/4] 创建项目 .venv …'
        Invoke-Checked $selected.executable @($selected.prefix + @('-m', 'venv', $venvDir))
    }
    Invoke-Checked $venvPython @('--version')
    $dependencyCheck = Join-Path $projectRoot 'scripts\check-local-deps.py'
    if (-not (Test-CommandQuietly $venvPython @($dependencyCheck, (Join-Path $backendDir 'requirements.txt')))) {
        Write-Host '[1/4] 安装基础后端依赖（不安装模型/RAG/OCR 依赖）…'
        Invoke-Checked $venvPython @('-m', 'pip', 'install', '--no-cache-dir', '--index-url', 'https://pypi.org/simple', '-r', (Join-Path $backendDir 'requirements.txt'))
    } else { Write-Host '[1/4] 基础后端依赖已就绪。' }
}

function Ensure-FrontendEnvironment {
    $script:nodePath = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
    $script:npmPath = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $script:nodePath -or -not $script:npmPath) { throw '未找到 Node.js/npm，请安装 Node.js 后重试。' }
    Invoke-Checked $script:nodePath @('--version')
    Push-Location $frontendDir
    try {
        if (-not (Test-CommandQuietly $script:nodePath @('--input-type=module', '-e', "await import('vite'); await import('vue'); await import('@vitejs/plugin-vue'); await import('element-plus')"))) {
            Write-Host '[2/4] 安装前端依赖 …'
            Invoke-Checked $script:npmPath @('install', '--no-audit', '--no-fund')
        } else { Write-Host '[2/4] 前端依赖已就绪。' }
    } finally { Pop-Location }
}

function Ensure-LocalConfiguration {
    $backendEnv = Join-Path $backendDir '.env'
    if (-not (Test-Path -LiteralPath $backendEnv)) {
        $template = Get-Content -LiteralPath (Join-Path $backendDir '.env.example') -Raw
        $randomBytes = New-Object byte[] 48
        $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
        $secret = [Convert]::ToBase64String($randomBytes)
        $template = [regex]::Replace($template, '(?m)^SECRET_KEY=.*$', "SECRET_KEY=$secret")
        $template = [regex]::Replace($template, '(?m)^OPENAI_API_KEY=.*$', 'OPENAI_API_KEY=')
        $template = [regex]::Replace($template, '(?m)^FIRST_SUPERUSER_PASSWORD=.*$', 'FIRST_SUPERUSER_PASSWORD=')
        $template = [regex]::Replace($template, '(?m)^OCR_DETECTION_MODEL_DIR=.*$', 'OCR_DETECTION_MODEL_DIR=../data/models/ocr/paddleocr/PP-OCRv5_mobile_det')
        $template = [regex]::Replace($template, '(?m)^OCR_RECOGNITION_MODEL_DIR=.*$', 'OCR_RECOGNITION_MODEL_DIR=../data/models/ocr/paddleocr/PP-OCRv5_mobile_rec')
        $template = [regex]::Replace($template, '(?m)^OCR_TEXTLINE_ORIENTATION_MODEL_DIR=.*$', 'OCR_TEXTLINE_ORIENTATION_MODEL_DIR=../data/models/ocr/paddleocr/PP-LCNet_x0_25_textline_ori')
        [IO.File]::WriteAllText($backendEnv, $template, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host '[3/4] 已生成 backend/.env（随机 JWT 密钥，未配置 API Key/管理员密码）。'
    } else { Write-Host '[3/4] 保留已有 backend/.env。' }
    $frontendEnv = Join-Path $frontendDir '.env'
    if (-not (Test-Path -LiteralPath $frontendEnv)) {
        [IO.File]::WriteAllText($frontendEnv, "VITE_API_BASE_URL=$backendUrl`r`n", (New-Object System.Text.UTF8Encoding($false)))
    }
    # These overrides affect only launcher children. Existing .env files are not read or rewritten.
    $dataDir = Join-Path $projectRoot 'data'
    $env:DATABASE_URL = 'sqlite:///' + (Join-Path $dataDir 'app.db').Replace('\', '/')
    $env:UPLOAD_DIR = Join-Path $dataDir 'uploads'
    $env:CHROMA_DIR = Join-Path $dataDir 'chroma'
    $env:LOG_DIR = Join-Path $dataDir 'logs'
    $env:API_V1_PREFIX = '/api/v1'
    $env:CORS_ORIGINS = '["http://localhost:5173","http://127.0.0.1:5173"]'
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $env:PREPROCESS_OCR_FALLBACK_ENABLED = 'false'
    $env:LITEPARSE_OCR_ENABLED = 'false'
    $env:PREPROCESS_LLM_ENABLED = 'false'
    $env:CHUNK_LLM_NORMALIZATION_ENABLED = 'false'
    $env:INGESTION_AGENT_LLM_ENABLED = 'false'
    $env:QUERY_AGENT_LLM_ENABLED = 'false'
    $env:QUERY_AGENT_EVIDENCE_LLM_ENABLED = 'false'
    $env:RERANKER_ENABLED = 'false'
    $env:PORT = '5173'
    $env:VITE_API_BASE_URL = $backendUrl
}

function Start-ServiceProcess([string]$Role) {
    $current = Get-OwnedProcess $Role
    if ($null -ne $current) {
        Write-Host "[4/4] $Role 已由本启动器运行，复用现有进程。"
        Wait-Service $Role
        return
    }
    $port = if ($Role -eq 'backend') { 8000 } else { 5173 }
    if (Test-PortOccupied $port) { throw "端口 $port 被其他进程占用；请先关闭对应程序。启动器不会结束其他程序。" }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
    $stdout = Join-Path $runtimeDir "$Role-$stamp.stdout.log"
    $stderr = Join-Path $runtimeDir "$Role-$stamp.stderr.log"
    if ($Role -eq 'backend') {
        $entryPoint = Join-Path $projectRoot 'scripts\run-local-backend.py'
        $quotedEntry = '"' + $entryPoint + '"'
        $process = Start-Process -FilePath $venvPython -ArgumentList @('-u', $quotedEntry) -WorkingDirectory $backendDir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    } else {
        $entryPoint = Join-Path $frontendDir 'scripts\dev.mjs'
        $quotedEntry = '"' + $entryPoint + '"'
        $process = Start-Process -FilePath $script:nodePath -ArgumentList @($quotedEntry, '--port', '5173') -WorkingDirectory $frontendDir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    }
    $script:services[$Role] = @{ process_id = $process.Id; start_ticks = $process.StartTime.ToUniversalTime().Ticks; stdout = $stdout; stderr = $stderr }
    [void]$script:startedNow.Add($Role)
    Save-LaunchState
    Write-Host "[4/4] 正在启动 $Role …"
    Wait-Service $Role
}

try {
    Read-LaunchState
    if ($Action -eq 'stop') {
        Stop-OwnedService 'frontend'
        Stop-OwnedService 'backend'
        Save-LaunchState
        Write-Host '本启动器管理的前后端服务已停止。'
        exit 0
    }
    if ($Action -eq 'check') {
        $healthy = $true
        foreach ($role in @('backend', 'frontend')) {
            $running = $null -ne (Get-OwnedProcess $role)
            $ready = $running -and (Test-Endpoint $role)
            Write-Host "$role running=$running ready=$ready"
            if (-not $ready) { $healthy = $false }
        }
        if ($healthy) { exit 0 } else { exit 1 }
    }
    Write-Host "项目：$projectRoot"
    foreach ($role in @('backend', 'frontend')) {
        $port = if ($role -eq 'backend') { 8000 } else { 5173 }
        if ((Test-PortOccupied $port) -and $null -eq (Get-OwnedProcess $role)) {
            throw "端口 $port 已被其他进程占用，已停止启动。"
        }
    }
    Ensure-PythonEnvironment
    Ensure-FrontendEnvironment
    Ensure-LocalConfiguration
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    Start-ServiceProcess 'backend'
    Start-ServiceProcess 'frontend'
    Write-Host "`n启动成功：$frontendUrl"
    Write-Host "API 文档：$backendUrl/docs"
    Write-Host "日志目录：$runtimeDir"
    if (Test-Path -LiteralPath (Join-Path $backendDir '.env.rag')) {
        Write-Host '已加载本地 BGE-M3 向量化与重排配置。'
    } elseif (Test-Path -LiteralPath (Join-Path $backendDir '.env.ocr')) {
        Write-Host '已加载本地 OCR 配置；真实向量化与模型问答仍需另行配置。'
    } else {
        Write-Host '首次可在页面注册普通用户。当前为基础离线模式，上传保存/任务可用，真实向量化与模型问答仍需另行配置。'
    }
    if (Test-Path -LiteralPath (Join-Path $backendDir '.env.llm')) {
        Write-Host 'LLM 模式由 backend/.env.llm 控制，凭据沿用现有 .env；实际模式见后端日志。'
    } else {
        Write-Host '未启用独立 LLM 配置，外部 API 调用保持关闭。'
    }
    Write-Host '关闭这个窗口不会停止服务；双击 STOP_LOCAL.bat 停止。'
    if (-not $NoBrowser) {
        try { Start-Process $frontendUrl | Out-Null }
        catch { Write-Host "浏览器未能自动打开，请手动访问 $frontendUrl。服务已就绪。" }
    }
    exit 0
} catch {
    foreach ($role in $script:startedNow) { Stop-OwnedService ([string]$role) }
    if ($script:startedNow.Count -gt 0) { Save-LaunchState }
    Write-Host "`n操作失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
