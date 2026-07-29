@echo off
REM 结束占用 8000 端口的进程（停顿标注工具）
setlocal
set PORT=8000

echo Looking for process on port %PORT% ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  echo Killing PID %%a ...
  taskkill /PID %%a /F
)

echo Done.
netstat -ano | findstr ":%PORT% " | findstr LISTENING
if errorlevel 1 echo Port %PORT% is free.
endlocal
