@echo off
rem Double-click to start IELTS Study on Windows. The browser opens by itself.
cd /d "%~dp0.."
where uv >nul 2>nul
if errorlevel 1 (
  echo uv is not installed. Install it first:  https://docs.astral.sh/uv/getting-started/installation/
  echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  pause
  exit /b 1
)
uv run ielts-study
pause
