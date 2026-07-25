@echo off
title 事件合约模拟交易系统 [新实例 :8001/:3002]
cd /d "C:\Users\26059\event-contract-sim\event-contract-sim-new\event-contract-sim\backend"

echo.
echo ========================================
echo  事件合约模拟交易系统 - 新实例
echo  后端 :8001 | 前端 :3002
echo  独立数据库，与旧实例完全隔离
echo ========================================
echo.

echo [后端] 启动中...
set BACKEND_PORT=8001
start "Backend-8001" cmd /c "python main.py"
timeout /t 4 /nobreak >nul

echo [前端] 启动中...
cd /d "C:\Users\26059\event-contract-sim\event-contract-sim-new\event-contract-sim\frontend"
set PORT=3002
set REACT_APP_API=http://localhost:8001
start "Frontend-3002" cmd /c "npx react-scripts start"
timeout /t 15 /nobreak >nul

echo.
echo ========================================
echo  新实例启动完成！
echo  后端: http://localhost:8001
echo  前端: http://localhost:3002
echo  原有实例 (:8000/:3001) 不受影响
echo  两个终端窗口独立运行，关闭此窗口不影响
echo ========================================
echo.
pause
