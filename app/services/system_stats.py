import os
import platform
import psutil
from datetime import datetime
try:
    import GPUtil # pyright: ignore[reportMissingImports]
except ImportError:
    GPUtil = None
try:
    import pynvml # pyright: ignore[reportMissingImports]
except ImportError:
    pynvml = None

# System stats helper functions extracted from OllamaService.

def get_vram_info():
    try:
        if pynvml:
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            pynvml.nvmlShutdown()
            return {
                'total': info.total,
                'used': info.used,
                'free': info.free,
                'percent': (info.used / info.total) * 100 if info.total > 0 else 0
            }
        if GPUtil:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                return {
                    'total': gpu.memoryTotal * 1024 * 1024,
                    'used': gpu.memoryUsed * 1024 * 1024,
                    'free': gpu.memoryFree * 1024 * 1024,
                    'percent': gpu.memoryUtil * 100
                }
        try:
            import subprocess
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.total,memory.used,memory.free', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5, check=False)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if lines:
                    parts = lines[0].split(',')
                    if len(parts) >= 3:
                        total = int(parts[0].strip()) * 1024 * 1024
                        used = int(parts[1].strip()) * 1024 * 1024
                        free = int(parts[2].strip()) * 1024 * 1024
                        return {
                            'total': total,
                            'used': used,
                            'free': free,
                            'percent': (used / total) * 100 if total > 0 else 0
                        }
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    except (OSError, ValueError):
        pass
    return {'total': 0, 'used': 0, 'free': 0, 'percent': 0}


def get_disk_info():
    try:
        if platform.system() == 'Windows':
            system_drive = os.environ.get('SystemDrive', 'C:') + '\\'
            usage = psutil.disk_usage(system_drive)
        else:
            usage = psutil.disk_usage('/')
        return {
            'total': usage.total,
            'free': usage.free,
            'used': usage.used,
            'percent': usage.percent
        }
    except (OSError, ValueError):
        try:
            current_dir = os.getcwd()
            drive = os.path.splitdrive(current_dir)[0] if platform.system() == 'Windows' else '/'
            usage = psutil.disk_usage(drive + ('\\' if platform.system() == 'Windows' else ''))
            return {
                'total': usage.total,
                'free': usage.free,
                'used': usage.used,
                'percent': usage.percent
            }
        except (OSError, ValueError):
            return {'total': 0, 'free': 0, 'used': 0, 'percent': 0}


def collect_system_stats():
    try:
        vram_info = get_vram_info()
        # Ensure all required keys are present
        for k in ['total', 'used', 'free', 'percent']:
            if k not in vram_info:
                vram_info[k] = 0
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'percent': psutil.virtual_memory().percent
            },
            'vram': vram_info,
            'disk': get_disk_info()
        }
    except (OSError, ValueError):
        return {
            'cpu_percent': 0,
            'memory': {'total': 0, 'available': 0, 'percent': 0},
            'vram': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
            'disk': {'total': 0, 'free': 0, 'percent': 0, 'used': 0}
        }


def models_memory_usage(running_models):
    try:
        system_memory = psutil.virtual_memory()
        system_vram = get_vram_info()
        memory_usage = {
            'system_ram': {
                'total': system_memory.total,
                'used': system_memory.used,
                'free': system_memory.available,
                'percent': system_memory.percent
            },
            'system_vram': system_vram,
            'models': []
        }
        for model in running_models:
            info = {
                'name': model.get('name'),
                'size': model.get('size', 'Unknown'),
                'size_bytes': model.get('size_bytes', 0),
                'estimated_ram_usage': 'N/A',
                'estimated_vram_usage': 'N/A'
            }
            try:
                if model.get('size'):
                    size_str = model['size'].upper()
                    if 'GB' in size_str:
                        info['size_bytes'] = int(float(size_str.replace('GB', '').strip()) * 1024 * 1024 * 1024)
                    elif 'MB' in size_str:
                        info['size_bytes'] = int(float(size_str.replace('MB', '').strip()) * 1024 * 1024)
                    elif 'KB' in size_str:
                        info['size_bytes'] = int(float(size_str.replace('KB', '').strip()) * 1024)
            except Exception:
                pass
            memory_usage['models'].append(info)
        return memory_usage
    except Exception as e:
        return {
            'system_ram': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
            'system_vram': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
            'models': [],
            'error': str(e)
        }


def append_system_stats_history(history_file_path):
    try:
        if os.path.exists(history_file_path):
            import json
            with open(history_file_path, 'r') as f:
                history = json.load(f)
        else:
            history = []
        current = collect_system_stats()
        current['timestamp'] = datetime.now().isoformat()
        history.append(current)
        history = history[-100:]
        with open(history_file_path, 'w') as f:
            import json
            json.dump(history, f, indent=2)
        return history
    except Exception:
        return []
