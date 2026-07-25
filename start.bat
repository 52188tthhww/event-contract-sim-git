@echo off
title 事件合约模拟交易系统
cd /d C:\Users\26059\event-contract-sim\backend

echo.
echo ========================================
echo  事件合约模拟交易系统
echo  后端 :8000 | 前端 :3001
echo ========================================
echo.

echo [后端] 启动中...
start "Backend-8000" cmd /c "python main.py"
timeout /t 4 /nobreak >nul

echo [前端] 启动中...
cd /d C:\Users\26059\event-contract-sim\frontend
start "Frontend-3001" cmd /c "npx react-scripts start"
timeout /t 15 /nobreak >nul

echo.
echo ========================================
echo  启动完成！
echo  后端: http://localhost:8000
echo  前端: http://localhost:3001
echo  两个终端窗口独立运行，关闭此窗口不影响
echo ========================================
echo.
pause
