@echo off
chcp 65001 >nul
setlocal
title EchoLoop

cd /d "%~dp0"

set "UV_CMD="
for %%I in (uv.exe) do set "UV_CMD=%%~$PATH:I"
if not defined UV_CMD if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_CMD=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV_CMD if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV_CMD=%USERPROFILE%\.cargo\bin\uv.exe"

if not defined UV_CMD (
  echo [EchoLoop] 未检测到 uv，请先安装 uv：
  echo   https://docs.astral.sh/uv/getting-started/installation/
  echo.
  echo 可在 PowerShell 中运行以下命令安装：
  echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  echo.
  pause
  exit /b 1
)

echo ==================================================
echo   EchoLoop 正在启动（首次运行将自动准备环境与词典）
echo   关闭此窗口或按 Ctrl+C 可停止本地服务
echo ==================================================
echo.

"%UV_CMD%" run echoloop %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
  echo [EchoLoop] 进程异常退出（退出码：%EXIT_CODE%）。
)
pause
exit /b %EXIT_CODE%
