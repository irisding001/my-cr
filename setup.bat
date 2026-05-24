@echo off
echo ====================================
echo   WhatsApp QC 质检系统 - 初始化
echo ====================================
echo.

echo [1/3] 安装 Python 依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo 错误：pip install 失败，请确认 Python 已安装
    pause
    exit /b 1
)

echo.
echo [2/3] 安装 Playwright 浏览器...
playwright install chromium
if %errorlevel% neq 0 (
    echo 错误：playwright install 失败
    pause
    exit /b 1
)

echo.
echo [3/3] 初始化完成！
echo.
echo 接下来请：
echo   1. 复制 .env.example 为 .env
echo   2. 在 .env 中填入你的 ANTHROPIC_API_KEY
echo   3. 运行 run.bat 开始质检
echo.
pause
