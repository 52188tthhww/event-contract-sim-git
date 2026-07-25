@echo off
title 事件合约系统 - 守护中 (勿关)
cd /d C:\Users\26059\event-contract-sim

:loop
echo [%time%] 检查服务...

netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo [%time%] 后端已断开，重启中...
    start "Backend-8000" cmd /c "cd backend && python main.py"
)

netstat -ano | findstr ":3001" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo [%time%] 前端已断开，重启中...
    start "Frontend-3001" cmd /c "cd frontend && npm start"
)

timeout /t 10 /nobreak >nul
goto loop
