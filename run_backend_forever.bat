@echo off
:loop
echo %date% %time% starting backend...
C:\Users\26059\AppData\Local\Programs\Python\Python313\python.exe C:\Users\26059\event-contract-sim\backend\main.py
echo %date% %time% backend stopped, restarting in 5s...
timeout /t 5 /nobreak >nul
goto loop
