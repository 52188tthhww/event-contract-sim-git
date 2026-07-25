"""
守护进程 — 双击运行，崩溃自动重启，关闭此窗口停止所有服务
"""
import subprocess, sys, time, os, signal

ROOT = r"C:\Users\26059\event-contract-sim"
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")
DETACHED = 0x00000008

def kill_port(port):
    try:
        out = subprocess.check_output(f'netstat -ano | findstr :{port}', shell=True, text=True)
        for line in out.splitlines():
            parts = line.split()
            if 'LISTENING' in line:
                pid = parts[-1]
                subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
                print(f"  释放端口 {port} (PID {pid})")
    except: pass

def start_backend():
    kill_port(8000)
    return subprocess.Popen(
        [sys.executable, "main.py"], cwd=BACKEND,
        creationflags=subprocess.CREATE_NEW_CONSOLE | DETACHED,
    )

def start_frontend():
    kill_port(3001)
    return subprocess.Popen(
        ["cmd", "/c", "npx react-scripts start"], cwd=FRONTEND,
        creationflags=subprocess.CREATE_NEW_CONSOLE | DETACHED,
    )

print("事件合约模拟交易系统 - 守护启动")
print()

kill_port(8000)
kill_port(3001)

print("启动后端...")
be = start_backend()
time.sleep(5)

print("启动前端...")
fe = start_frontend()
time.sleep(2)

print()
print("=" * 45)
print("  后端  http://localhost:8000")
print("  前端  http://localhost:3001")
print("  守护中 — 崩溃自重启 — 关窗即停")
print("=" * 45)
print()

try:
    while True:
        time.sleep(10)
        if be.poll() is not None:
            print("[守护] 后端崩溃，重启中...")
            be = start_backend()
except KeyboardInterrupt:
    pass

print("停止服务...")
try: be.kill()
except: pass
try: fe.kill()
except: pass
print("已退出")
