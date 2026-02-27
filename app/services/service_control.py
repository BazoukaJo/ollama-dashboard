import platform, subprocess, time, os

# Platform-specific start/stop helpers extracted from OllamaService.

def start_service_windows(get_status):
    methods_tried = []
    if platform.system() != 'Windows':
        return None, methods_tried
    try:
        methods_tried.append('Windows service')
        result = subprocess.run(['sc', 'start', 'Ollama'], capture_output=True, text=True, timeout=15)
        if result.returncode == 0 or 'START_PENDING' in result.stdout:
            time.sleep(5)
            if get_status():
                return {"success": True, "message": "Ollama service started successfully via Windows service"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('installation path')
        paths = [r"C:\Program Files\Ollama\ollama.exe",
                 r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
                 r"C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe",
                 os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe")]
        for p in paths:
            ep = os.path.expandvars(os.path.expanduser(p))
            if os.path.exists(ep):
                try:
                    subprocess.Popen([ep, 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                                     close_fds=True, cwd=os.path.dirname(ep))
                except Exception:
                    pass
                time.sleep(5)
                if get_status():
                    return {"success": True, "message": f"Ollama service started successfully from {ep}"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('direct execution')
        check = subprocess.run(['where', 'ollama'], capture_output=True, text=True, timeout=5)
        if check.returncode == 0:
            try:
                subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS, close_fds=True)
            except Exception:
                pass
            time.sleep(5)
            if get_status():
                return {"success": True, "message": "Ollama service started successfully via direct execution"}, methods_tried
    except Exception:
        pass
    return None, methods_tried

def start_service_unix(get_status):
    methods_tried = []
    if platform.system() == 'Windows':
        return None, methods_tried
    try:
        methods_tried.append('systemctl')
        result = subprocess.run(['systemctl', 'start', 'ollama'], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            time.sleep(5)
            if get_status():
                return {"success": True, "message": "Ollama service started successfully via systemctl"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('service command')
        result = subprocess.run(['service', 'ollama', 'start'], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            time.sleep(5)
            if get_status():
                return {"success": True, "message": "Ollama service started successfully via service command"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('direct execution')
        check = subprocess.run(['which', 'ollama'], capture_output=True, text=True, timeout=5)
        if check.returncode == 0:
            try:
                subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            time.sleep(5)
            if get_status():
                return {"success": True, "message": "Ollama service started successfully via direct execution"}, methods_tried
    except Exception:
        pass
    return None, methods_tried

def stop_service_windows(get_status):
    methods_tried = []
    if platform.system() != 'Windows':
        return None, methods_tried
    try:
        methods_tried.append('Windows service')
        result = subprocess.run(['sc', 'stop', 'Ollama'], capture_output=True, text=True, timeout=15)
        if result.returncode == 0 or 'STOP_PENDING' in result.stdout:
            time.sleep(5)
            if not get_status():
                return {"success": True, "message": "Ollama service stopped successfully via Windows service"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('process termination')
        subprocess.run(['taskkill', '/IM', 'ollama.exe'], capture_output=True, text=True, timeout=10)
        time.sleep(5)
        if not get_status():
            return {"success": True, "message": "Ollama service stopped successfully via graceful termination"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('force kill')
        subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], capture_output=True, text=True, timeout=10)
        time.sleep(5)
        if not get_status():
            return {"success": True, "message": "Ollama service stopped successfully via force kill"}, methods_tried
    except Exception:
        pass
    return None, methods_tried

def stop_service_unix(get_status):
    methods_tried = []
    if platform.system() == 'Windows':
        return None, methods_tried
    try:
        methods_tried.append('systemctl')
        result = subprocess.run(['systemctl', 'stop', 'ollama'], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            time.sleep(5)
            if not get_status():
                return {"success": True, "message": "Ollama service stopped successfully via systemctl"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('service command')
        result = subprocess.run(['service', 'ollama', 'stop'], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            time.sleep(5)
            if not get_status():
                return {"success": True, "message": "Ollama service stopped successfully via service command"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('pkill graceful')
        subprocess.run(['pkill', '-TERM', '-f', 'ollama'], capture_output=True, text=True, timeout=10)
        time.sleep(3)
        if not get_status():
            return {"success": True, "message": "Ollama service stopped successfully via graceful pkill"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('pkill force')
        subprocess.run(['pkill', '-9', '-f', 'ollama'], capture_output=True, text=True, timeout=10)
        time.sleep(3)
        if not get_status():
            return {"success": True, "message": "Ollama service stopped successfully via force pkill"}, methods_tried
    except Exception:
        pass
    try:
        methods_tried.append('killall')
        subprocess.run(['killall', '-TERM', 'ollama'], capture_output=True, text=True, timeout=10)
        time.sleep(3)
        if not get_status():
            return {"success": True, "message": "Ollama service stopped successfully via killall"}, methods_tried
    except Exception:
        pass
    return None, methods_tried
