@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

rem Validate the interpreter; py.exe can exist without a registered Python.
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if not errorlevel 1 goto run_python
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul
if not errorlevel 1 goto run_py

echo 未找到可用的 Python 3.10 或更高版本。请检查 python 或 py 命令。
pause
exit /b 1

:run_python
python "%~dp0app.py" %*
goto finished

:run_py
py -3 "%~dp0app.py" %*

:finished
set "cleaner_exit=%errorlevel%"
if not "%cleaner_exit%"=="0" echo 启动或运行失败，请查看上方的具体错误。
pause
exit /b %cleaner_exit%
