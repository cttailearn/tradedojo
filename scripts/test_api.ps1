# TradeDojo 端到端 API 冒烟测试
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$cookieJar = Join-Path $env:TEMP "tdj_test.cookies"
Remove-Item $cookieJar -ErrorAction SilentlyContinue

function Get-CookiePath { $script:cookieJar }

function Invoke-Test {
    param(
        [string]$Title,
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = @{},
        [string]$Body = $null
    )
    Write-Host "===== $Title =====" -ForegroundColor Cyan
    $args = @("-sS", "-X", $Method, $Url)
    foreach ($k in $Headers.Keys) { $args += @("-H", "$k`: $($Headers[$k])") }
    if ($Body) {
        $tmp = New-TemporaryFile
        [System.IO.File]::WriteAllText($tmp.FullName, $Body, [System.Text.Encoding]::UTF8)
        $args += @("--data-binary", "@$($tmp.FullName)")
        $args += @("-H", "Content-Type: application/json")
    }
    if ($script:cookieJar -and (Test-Path $script:cookieJar)) {
        $args += @("-b", $script:cookieJar)
    }
    $args += @("-c", $script:cookieJar)
    $args += @("-w", "`nHTTP %{http_code}`n")
    & curl.exe @args
    Remove-Item $tmp -ErrorAction SilentlyContinue
    Write-Host ""
}

# 1. 健康检查
Invoke-Test "1. 健康检查" "GET" "http://127.0.0.1:8000/api/health"

# 2. 错误密码
Invoke-Test "2. 错误密码登录 (期望 401)" "POST" "http://127.0.0.1:8000/api/auth/login" @{} '{"username":"ctt","password":"wrong_pwd"}'

# 3. 正确密码登录
Invoke-Test "3. 正确密码登录 (ctt/ctt584520)" "POST" "http://127.0.0.1:8000/api/auth/login" @{} '{"username":"ctt","password":"ctt584520"}'

# 4. /api/auth/me (cookie 自动带)
Invoke-Test "4. /api/auth/me (凭 cookie)" "GET" "http://127.0.0.1:8000/api/auth/me"

# 5. 训练端注册
$ts = Get-Date -Format "HHmmss"
$trainUser = "t_$ts"
Invoke-Test "5. 训练端注册" "POST" "http://127.0.0.1:8000/api/train/register" @{} "{`"username`":`"$trainUser`",`"password`":`"abcd1234`",`"nickname`":`"测试`"}"

# 6. 训练端登录
Invoke-Test "6. 训练端登录" "POST" "http://127.0.0.1:8000/api/train/login" @{} "{`"username`":`"$trainUser`",`"password`":`"abcd1234`"}"

# 7. 训练端 /api/train/me
Invoke-Test "7. 训练端 /api/train/me" "GET" "http://127.0.0.1:8000/api/train/me"

# 8. 训练端钱包
Invoke-Test "8. 训练端 /api/train/wallet" "GET" "http://127.0.0.1:8000/api/train/wallet"

# 9. 业务接口:股票列表 (admin cookie)
Invoke-Test "9. /api/stocks 列表" "GET" "http://127.0.0.1:8000/api/stocks?page=1&page_size=5"

# 10. 业务接口:系统状态
Invoke-Test "10. /api/system/status" "GET" "http://127.0.0.1:8000/api/system/status"

# 11. 限速测试:连发 25 次错误登录(limit=20/min)
Write-Host "===== 11. 限速测试(连发 25 次错误密码)=====" -ForegroundColor Cyan
for ($i=1; $i -le 25; $i++) {
    $code = & curl.exe -sS -o /dev/null -w "%{http_code}" -X POST -b $script:cookieJar -c $script:cookieJar -H "Content-Type: application/json" http://127.0.0.1:8000/api/auth/login -d ('{"username":"ctt","password":"x'$i'"}')
    if ($i % 5 -eq 0) { Write-Host "  attempt #$i -> $code" }
}
Write-Host ""

# 12. 用错误 token 测一下 401
Write-Host "===== 12. 伪造 Bearer token (期望 401) =====" -ForegroundColor Cyan
& curl.exe -sS -X GET -H "Authorization: Bearer fake.invalid.token" http://127.0.0.1:8000/api/auth/me -w "`nHTTP %{http_code}`n"
Write-Host ""

# 13. CORS 预检
Write-Host "===== 13. CORS 预检 =====" -ForegroundColor Cyan
& curl.exe -sS -i -X OPTIONS http://127.0.0.1:8000/api/auth/login -H "Origin: http://localhost:5173" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type" 2>&1 | Select-String -Pattern "HTTP|Access-Control"
Write-Host ""

Write-Host "===== Cookie 状态 =====" -ForegroundColor Cyan
if (Test-Path $script:cookieJar) {
    Get-Content $script:cookieJar | Select-String -Pattern "tdj_" -Context 0,1
} else {
    Write-Host "(无 cookie 文件)"
}