@echo off
setlocal

REM ==========================================
REM 自动环境配置与启动脚本
REM ==========================================

REM 切换到脚本所在目录，确保相对路径正确
cd /d "%~dp0"

REM 定义变量
set "VENV_DIR=venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "PIP_EXE=%VENV_DIR%\Scripts\pip.exe"
set "MAIN_SCRIPT=app\main.py"
set "REQ_FILE=app\requirements.txt"

REM 1. 检查虚拟环境是否存在
if exist "%VENV_DIR%\" (
    echo [INFO] 检测到虚拟环境，准备启动...
    goto :START_APP
)

REM 2. 如果不存在，创建虚拟环境
echo [WARN] 未检测到虚拟环境 (venv)，正在自动创建...
echo [INFO] 请稍候，这可能需要几分钟...

REM 尝试调用系统 Python 创建 venv
python -m venv "%VENV_DIR%"

REM 检查创建是否成功
if not exist "%PYTHON_EXE%" (
    echo [ERROR] 虚拟环境创建失败！
    echo [HINT] 请确保你已经安装了 Python (3.10+) 并且添加到了系统环境变量 PATH 中。
    pause
    exit /b 1
)

REM 3. 安装依赖
echo [INFO] 正在安装依赖包...
if exist "%REQ_FILE%" (
    "%PIP_EXE%" install --upgrade pip
    "%PIP_EXE%" install -r "%REQ_FILE%"
    
    if %errorlevel% neq 0 (
        echo [ERROR] 依赖安装失败！请检查网络连接或 pip 源。
        pause
        exit /b 1
    )
) else (
    echo [WARN] 未找到 requirements.txt，跳过依赖安装。
)

echo [INFO] 环境部署完成！

:START_APP
REM 4. 启动主程序
echo [INFO] 正在启动应用程序...

REM 使用 python.exe 启动 (保留控制台以便查看日志)
REM 如果想要无黑框启动，可以将下方的 python.exe 改为 pythonw.exe
"%PYTHON_EXE%" "%MAIN_SCRIPT%"

REM 如果程序异常退出（返回码不为0），暂停显示错误信息
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] 程序异常退出。请检查上方错误信息。
    pause
)

endlocal