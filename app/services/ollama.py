from flask import current_app
import requests
from datetime import datetime, timezone, timedelta
import time
import json
import os
from collections import deque
import psutil
import threading
import atexit

class OllamaService:
    def __init__(self, app=None):
        self.app = app
        # Performance optimizations
        self._cache = {}
        self._cache_timestamps = {}
        self._session = requests.Session()  # Connection pooling
        self._background_stats = None
        self._stats_lock = threading.Lock()
        self._stop_background = threading.Event()

        if app is not None:
            self.init_app(app)
        else:
            self.history = deque(maxlen=50)  # Default max history

    def init_app(self, app):
        """Initialize the service with the Flask app"""
        self.app = app
        with self.app.app_context():
            self.history = self.load_history()

        # Start background data collection
        self._start_background_updates()

        # Register cleanup
        atexit.register(self._cleanup)

    def _start_background_updates(self):
        """Start background data collection for all data types"""
        if self._background_stats and self._background_stats.is_alive():
            return

        self._stop_background.clear()
        self._background_stats = threading.Thread(
            target=self._background_updates_worker,
            daemon=True,
            name="BackgroundDataCollector"
        )
        self._background_stats.start()

    def _background_updates_worker(self):
        """Background worker for collecting all data types"""
        while not self._stop_background.is_set():
            try:
                # Collect system stats
                stats = self._get_system_stats_raw()
                with self._stats_lock:
                    self._cache['system_stats'] = stats
                    self._cache_timestamps['system_stats'] = datetime.now()

                # Collect running models (every 10 seconds)
                if not hasattr(self, '_model_update_counter'):
                    self._model_update_counter = 0
                self._model_update_counter += 1

                if self._model_update_counter >= 5:  # Every 10 seconds (5 * 2)
                    try:
                        # Get and process running models (same logic as get_running_models method)
                        response = self._session.get(self.get_api_url(), timeout=5)
                        if response.status_code == 200:
                            data = response.json()
                            models = data.get('models', [])

                            # Process models the same way as get_running_models
                            current_models = []
                            for model in models:
                                # Format size
                                model['formatted_size'] = self.format_size(model['size'])

                                # Format families
                                families = model.get('details', {}).get('families', [])
                                if families:
                                    model['families_str'] = ', '.join(families)
                                else:
                                    model['families_str'] = model.get('details', {}).get('family', 'Unknown')

                                # Detect and add capabilities
                                capabilities = self._detect_model_capabilities(model)
                                model['has_vision'] = capabilities['has_vision']
                                model['has_tools'] = capabilities['has_tools']
                                model['has_reasoning'] = capabilities['has_reasoning']

                                # Format expiration times
                                if model.get('expires_at'):
                                    if model['expires_at'] == 'Stopping':
                                        model['expires_at'] = {
                                            'local': 'Stopping...',
                                            'relative': 'Process is stopping'
                                        }
                                    else:
                                        try:
                                            # Handle microseconds by truncating them
                                            expires_at = model['expires_at'].replace('Z', '+00:00')
                                            expires_at = expires_at.split('.')[0] + '+00:00'
                                            expires_dt = datetime.fromisoformat(expires_at)
                                            local_dt = expires_dt.astimezone()
                                            relative_time = self.format_relative_time(expires_dt)
                                            tz_abbr = time.strftime('%Z')
                                            model['expires_at'] = {
                                                'local': local_dt.strftime(f'%-I:%M %p, %b %-d ({tz_abbr})'),
                                                'relative': relative_time
                                            }
                                        except Exception as e:
                                            model['expires_at'] = None

                                current_models.append({
                                    'name': model['name'],
                                    'families_str': model.get('families_str', ''),
                                    'parameter_size': model.get('details', {}).get('parameter_size', ''),
                                    'size': model.get('formatted_size', ''),
                                    'expires_at': model.get('expires_at'),
                                    'details': model.get('details', {}),
                                    'has_vision': model.get('has_vision', False),
                                    'has_tools': model.get('has_tools', False),
                                    'has_reasoning': model.get('has_reasoning', False)
                                })

                            with self._stats_lock:
                                self._cache['running_models'] = current_models
                                self._cache_timestamps['running_models'] = datetime.now()
                    except Exception as e:
                        print(f"Background model collection error: {e}")

                    # Get available models (every 30 seconds)
                    if self._model_update_counter >= 15:  # Every 30 seconds (15 * 2)
                        try:
                            if self.app:
                                host = self.app.config.get('OLLAMA_HOST')
                                port = self.app.config.get('OLLAMA_PORT')
                            else:
                                host = os.getenv('OLLAMA_HOST', 'localhost')
                                port = int(os.getenv('OLLAMA_PORT', 11434))

                            tags_url = f"http://{host}:{port}/api/tags"
                            response = self._session.get(tags_url, timeout=10)
                            if response.status_code == 200:
                                models = response.json().get('models', [])
                                with self._stats_lock:
                                    self._cache['available_models'] = models
                                    self._cache_timestamps['available_models'] = datetime.now()
                        except Exception as e:
                            print(f"Background available models collection error: {e}")

                        # Get Ollama version (every 5 minutes)
                        try:
                            version_url = f"http://{host}:{port}/api/version"
                            response = self._session.get(version_url, timeout=5)
                            if response.status_code == 200:
                                data = response.json()
                                version = data.get('version', 'Unknown')
                                with self._stats_lock:
                                    self._cache['ollama_version'] = version
                                    self._cache_timestamps['ollama_version'] = datetime.now()
                        except Exception as e:
                            print(f"Background version collection error: {e}")

                        self._model_update_counter = 0  # Reset counter

            except Exception as e:
                print(f"Background updates error: {e}")

            # Sleep for 2 seconds between collections
            self._stop_background.wait(2)

    def _cleanup(self):
        """Cleanup background threads"""
        self._stop_background.set()
        if self._background_stats:
            self._background_stats.join(timeout=1)
        self._session.close()

    def _get_cached(self, key, ttl_seconds=30):
        """Get cached data if still valid"""
        if key in self._cache_timestamps:
            age = (datetime.now() - self._cache_timestamps[key]).total_seconds()
            if age < ttl_seconds:
                return self._cache.get(key)
        return None

    def _set_cached(self, key, data):
        """Cache data with timestamp"""
        self._cache[key] = data
        self._cache_timestamps[key] = datetime.now()

    def get_api_url(self):
        try:
            # Get host and port from app config if available, otherwise use environment/defaults
            if self.app:
                host = self.app.config.get('OLLAMA_HOST')
                port = self.app.config.get('OLLAMA_PORT')
            else:
                import os
                host = os.getenv('OLLAMA_HOST', 'localhost')
                port = int(os.getenv('OLLAMA_PORT', 11434))

            if not host or not port:
                raise ValueError(f"Missing configuration: OLLAMA_HOST={host}, OLLAMA_PORT={port}")
            return f"http://{host}:{port}/api/ps"
        except Exception as e:
            raise Exception(f"Failed to connect to Ollama server: {str(e)}. Please ensure Ollama is running and accessible.")

    def format_size(self, size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"

    def format_relative_time(self, target_dt):
        now = datetime.now(timezone.utc)
        diff = target_dt - now

        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60

        if days > 0:
            if hours > 12:
                days += 1
            return f"about {days} {'day' if days == 1 else 'days'}"
        elif hours > 0:
            if minutes > 30:
                hours += 1
            return f"about {hours} {'hour' if hours == 1 else 'hours'}"
        elif minutes > 0:
            if minutes < 5:
                return "a few minutes"
            elif minutes < 15:
                return "about 10 minutes"
            elif minutes < 25:
                return "about 20 minutes"
            elif minutes < 45:
                return "about 30 minutes"
            else:
                return "about an hour"
        else:
            return "less than a minute"

    def get_ollama_version(self):
        # Check cache first (version changes rarely)
        cached = self._get_cached('ollama_version', ttl_seconds=300)  # 5 minutes
        if cached is not None:
            return cached

        try:
            version_url = f"http://{self.app.config.get('OLLAMA_HOST')}:{self.app.config.get('OLLAMA_PORT')}/api/version"
            response = self._session.get(version_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            version = data.get('version', 'Unknown')
            self._set_cached('ollama_version', version)
            return version
        except Exception as e:
            return 'Unknown'

    def get_system_stats(self):
        """Get basic system statistics"""
        # Check cache first (system stats are collected in background)
        cached = self._get_cached('system_stats', ttl_seconds=5)  # 5 seconds
        if cached is not None:
            return cached

        # Fallback to direct collection if cache miss
        return self._get_system_stats_raw()

    def _get_system_stats_raw(self):
        """Get system stats without caching (used by background worker)"""
        try:
            import psutil

            # Get VRAM information
            vram_info = self._get_vram_info()

            return {
                'cpu_percent': psutil.cpu_percent(interval=0.1),  # Much faster, no blocking
                'memory': {
                    'total': psutil.virtual_memory().total,
                    'available': psutil.virtual_memory().available,
                    'percent': psutil.virtual_memory().percent
                },
                'vram': vram_info,
                'disk': self._get_disk_info()
            }
        except ImportError:
            # Return mock data if psutil is not available
            return {
                'cpu_percent': 25.5,
                'memory': {
                    'total': 17179869184,  # 16GB
                    'available': 8589934592,  # 8GB
                    'percent': 50.0
                },
                'vram': {
                    'total': 8589934592,  # 8GB
                    'used': 2147483648,   # 2GB
                    'free': 6442450944,   # 6GB
                    'percent': 25.0
                },
                'disk': {
                    'total': 1000204886016,  # ~1TB
                    'free': 500000000000,   # ~500GB
                    'percent': 50.0
                }
            }
        except Exception as e:
            return {
                'cpu_percent': 0,
                'memory': {
                    'total': 0,
                    'available': 0,
                    'percent': 0
                },
                'vram': {
                    'total': 0,
                    'used': 0,
                    'free': 0,
                    'percent': 0
                },
                'disk': {
                    'total': 0,
                    'free': 0,
                    'percent': 0
                }
            }

    def _get_vram_info(self):
        """Get VRAM (GPU memory) information"""
        try:
            # Try to get NVIDIA GPU memory info
            try:
                import pynvml
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
            except (ImportError, Exception):
                pass

            # Try GPUtil for GPU info
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]  # Get first GPU
                    return {
                        'total': gpu.memoryTotal * 1024 * 1024,  # Convert MB to bytes
                        'used': gpu.memoryUsed * 1024 * 1024,
                        'free': gpu.memoryFree * 1024 * 1024,
                        'percent': gpu.memoryUtil * 100
                    }
            except (ImportError, Exception):
                pass

            # Fallback: Try to get GPU info from system
            try:
                import subprocess
                # Try nvidia-smi command
                result = subprocess.run(['nvidia-smi', '--query-gpu=memory.total,memory.used,memory.free', '--format=csv,noheader,nounits'],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if lines:
                        parts = lines[0].split(',')
                        if len(parts) >= 3:
                            total = int(parts[0].strip()) * 1024 * 1024  # Convert MB to bytes
                            used = int(parts[1].strip()) * 1024 * 1024
                            free = int(parts[2].strip()) * 1024 * 1024
                            return {
                                'total': total,
                                'used': used,
                                'free': free,
                                'percent': (used / total) * 100 if total > 0 else 0
                            }
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                pass

        except Exception:
            pass

        # Return default VRAM info if no GPU detected
        return {
            'total': 0,
            'used': 0,
            'free': 0,
            'percent': 0
        }

    def _get_disk_info(self):
        """Get disk usage information for the system drive."""
        try:
            import platform

            if platform.system() == "Windows":
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

        except Exception:
            # Fallback: try to get disk info for current directory
            try:
                current_dir = os.getcwd()
                drive = os.path.splitdrive(current_dir)[0] if platform.system() == "Windows" else '/'
                usage = psutil.disk_usage(drive + ('\\' if platform.system() == "Windows" else ''))
                return {
                    'total': usage.total,
                    'free': usage.free,
                    'used': usage.used,
                    'percent': usage.percent
                }
            except Exception:
                # Last resort: return zeros
                return {
                    'total': 0,
                    'free': 0,
                    'used': 0,
                    'percent': 0
                }

    def _detect_model_capabilities(self, model):
        """Detect capabilities for a model based on metadata."""
        capabilities = {
            'has_vision': False,
            'has_tools': False,
            'has_reasoning': False
        }

        model_name = model.get('name', '').lower()
        details = model.get('details', {}) or {}
        families = details.get('families', []) or []

        # Tokenize model name for precise matching (avoid substring false positives)
        import re
        tokens = re.split(r'[\-_:]', model_name)
        token_set = set(tokens)

        # --- Vision Detection ---
        # Strict allowlist of known vision model base identifiers
        vision_allow = {
            'llava', 'bakllava', 'moondream', 'qwen2-vl', 'qwen2.5-vl', 'qwen3-vl',
            'llava-llama3', 'llava-phi3', 'cogvlm', 'yi-vl', 'deepseek-vl', 'paligemma', 'fuyu', 'idefics'
        }
        # Pattern: qwen* with '-vl' suffix
        if any(v in model_name for v in vision_allow):
            capabilities['has_vision'] = True
        # Families heuristic: presence of vision encoders
        if isinstance(families, list):
            for fam in families:
                fam_l = str(fam).lower()
                if any(x in fam_l for x in ['clip', 'projector', 'vision', 'multimodal', 'vl']):
                    capabilities['has_vision'] = True
                    break
        elif isinstance(families, str):
            fam_l = families.lower()
            if any(x in fam_l for x in ['clip', 'projector', 'vision', 'multimodal', 'vl']):
                capabilities['has_vision'] = True

        # --- Tool / Function Calling Detection ---
        # Allowlist of bases known to expose tool/function calling in Ollama or upstream releases
        tool_allow_exact = {
            'llama3.1', 'llama3.2', 'llama3.3',
            'mistral', 'mixtral', 'command-r', 'command-r-plus',
            'firefunction', 'qwen2.5', 'qwen3', 'granite3', 'hermes3', 'nemotron'
        }
        # Version exclusions / older variants without tooling
        tool_exclude = {'llama3.0', 'qwen2.0', 'hermes2', 'hermes-2'}

        # Match by prefix tokens (e.g. llama3.1:8b => startswith llama3.1)
        if any(model_name.startswith(t) for t in tool_allow_exact) and not any(model_name.startswith(e) for e in tool_exclude):
            capabilities['has_tools'] = True

        # Secondary heuristic: if a later version appears (e.g. llama3.2) treat as tools-capable
        version_pattern_match = re.search(r'(llama3\.[1-9])', model_name)
        if version_pattern_match and version_pattern_match.group(1) not in tool_exclude:
            capabilities['has_tools'] = True

        # Qwen pattern: qwen3 or qwen2.5 variants (not plain qwen)
        if re.search(r'qwen(2\.5|3)', model_name):
            capabilities['has_tools'] = True

        # --- Reasoning Detection ---
        reasoning_allow = {
            'deepseek-r1', 'qwq', 'marco-o1', 'k0-math'
        }
        if any(r in model_name for r in reasoning_allow):
            capabilities['has_reasoning'] = True

        # Pattern heuristics: models containing explicit reasoning suffixes/tokens
        reasoning_token_triggers = {'reasoning', 'cot', 'chain-of-thought', 'think'}
        if any(tok in model_name for tok in reasoning_token_triggers):
            capabilities['has_reasoning'] = True

        # R1 token heuristic: token 'r1' preceded by alphabetic base (avoid matching 'v1')
        if 'r1' in token_set and not any(t.startswith('v1') for t in token_set):
            if any(base in model_name for base in ['deepseek', 'llama', 'qwen', 'phi', 'mixtral']):
                capabilities['has_reasoning'] = True

        return capabilities

    def get_available_models(self):
        """Get list of available models (not just running ones)."""
        # Check cache first (models list changes infrequently)
        cached = self._get_cached('available_models', ttl_seconds=60)  # 1 minute
        if cached is not None:
            return cached

        try:
            if self.app:
                host = self.app.config.get('OLLAMA_HOST')
                port = self.app.config.get('OLLAMA_PORT')
            else:
                host = os.getenv('OLLAMA_HOST', 'localhost')
                port = int(os.getenv('OLLAMA_PORT', 11434))

            tags_url = f"http://{host}:{port}/api/tags"
            response = self._session.get(tags_url, timeout=10)
            response.raise_for_status()
            models = response.json().get('models', [])

            # Add capabilities to each model
            for model in models:
                capabilities = self._detect_model_capabilities(model)
                # Explicitly set each capability to override any None values
                model['has_vision'] = capabilities['has_vision']
                model['has_tools'] = capabilities['has_tools']
                model['has_reasoning'] = capabilities['has_reasoning']

            self._set_cached('available_models', models)
            return models
        except Exception:
            return []

    def get_running_models(self):
        # Check cache first (running models change more frequently)
        cached = self._get_cached('running_models', ttl_seconds=10)  # 10 seconds
        if cached is not None:
            return cached

        try:
            response = self._session.get(self.get_api_url(), timeout=5)
            response.raise_for_status()
            data = response.json()
            models = data.get('models', [])

            current_models = []
            for model in models:
                # Format size
                model['formatted_size'] = self.format_size(model['size'])

                # Format families
                families = model.get('details', {}).get('families', [])
                if families:
                    model['families_str'] = ', '.join(families)
                else:
                    model['families_str'] = model.get('details', {}).get('family', 'Unknown')

                # Detect and add capabilities
                capabilities = self._detect_model_capabilities(model)
                model['has_vision'] = capabilities['has_vision']
                model['has_tools'] = capabilities['has_tools']
                model['has_reasoning'] = capabilities['has_reasoning']

                # Format expiration times
                if model.get('expires_at'):
                    if model['expires_at'] == 'Stopping':
                        model['expires_at'] = {
                            'local': 'Stopping...',
                            'relative': 'Process is stopping'
                        }
                    else:
                        try:
                            # Handle microseconds by truncating them
                            expires_at = model['expires_at'].replace('Z', '+00:00')
                            expires_at = expires_at.split('.')[0] + '+00:00'
                            expires_dt = datetime.fromisoformat(expires_at)
                            local_dt = expires_dt.astimezone()
                            relative_time = self.format_relative_time(expires_dt)
                            tz_abbr = time.strftime('%Z')
                            model['expires_at'] = {
                                'local': local_dt.strftime(f'%-I:%M %p, %b %-d ({tz_abbr})'),
                                'relative': relative_time
                            }
                        except Exception as e:
                            model['expires_at'] = None

                current_models.append({
                    'name': model['name'],
                    'families_str': model.get('families_str', ''),
                    'parameter_size': model.get('details', {}).get('parameter_size', ''),
                    'size': model.get('formatted_size', ''),
                    'expires_at': model.get('expires_at'),
                    'details': model.get('details', {}),
                    'has_vision': model.get('has_vision', False),
                    'has_tools': model.get('has_tools', False),
                    'has_reasoning': model.get('has_reasoning', False)
                })

            if current_models:
                self.update_history(current_models)

            self._set_cached('running_models', current_models)
            return current_models
        except requests.exceptions.ConnectionError:
            raise Exception("Could not connect to Ollama server. Please ensure it's running and accessible.")
        except requests.exceptions.Timeout:
            raise Exception("Connection to Ollama server timed out. Please check your network connection.")
        except Exception as e:
            raise Exception(f"Error fetching models: {str(e)}")

    def load_history(self):
        try:
            if not self.app:
                return deque(maxlen=50)  # Default max history when no app context

            history_file = self.app.config['HISTORY_FILE']
            max_history = self.app.config['MAX_HISTORY']

            if os.path.exists(history_file):
                with open(history_file, 'r') as f:
                    history = json.load(f)
                    return deque(history, maxlen=max_history)
            else:
                with open(history_file, 'w') as f:
                    json.dump([], f)
                return deque(maxlen=max_history)
        except Exception as e:
            print(f"Error handling history file: {str(e)}")
            return deque(maxlen=50)  # Default max history

    def update_history(self, models):
        timestamp = datetime.now().isoformat()
        self.history.appendleft({
            'timestamp': timestamp,
            'models': models
        })
        self.save_history()

    def save_history(self):
        if not self.app:
            return  # Skip saving when no app context
        with open(self.app.config['HISTORY_FILE'], 'w') as f:
            json.dump(list(self.history), f)

    def format_datetime(self, value):
        try:
            if isinstance(value, str):
                # Handle timezone offset in the ISO format string
                dt = datetime.fromisoformat(value.replace('Z', '+00:00').split('.')[0])
            else:
                dt = value
            local_dt = dt.astimezone()
            tz_abbr = time.strftime('%Z')
            return local_dt.strftime(f'%-I:%M %p, %b %-d ({tz_abbr})')
        except Exception as e:
            return str(value)

    def format_time_ago(self, value):
        try:
            if isinstance(value, str):
                # Handle timezone offset in the ISO format string
                dt = datetime.fromisoformat(value.replace('Z', '+00:00').split('.')[0])
            else:
                dt = value

            now = datetime.now(dt.tzinfo)
            diff = now - dt

            minutes = diff.total_seconds() / 60
            hours = minutes / 60

            if hours >= 1:
                return f"{int(hours)} {'hour' if int(hours) == 1 else 'hours'}"
            elif minutes >= 1:
                return f"{int(minutes)} {'minute' if int(minutes) == 1 else 'minutes'}"
            else:
                return "less than a minute"
        except Exception as e:
            return str(value)

    def get_chat_history(self):
        """Get chat history"""
        try:
            chat_history_file = os.path.join(os.path.dirname(self.app.config['HISTORY_FILE']), 'chat_history.json')
            if os.path.exists(chat_history_file):
                with open(chat_history_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            print(f"Error loading chat history: {str(e)}")
            return []

    def save_chat_session(self, session_data):
        """Save a chat session"""
        try:
            chat_history_file = os.path.join(os.path.dirname(self.app.config['HISTORY_FILE']), 'chat_history.json')
            history = self.get_chat_history()

            # Add timestamp if not present
            if 'timestamp' not in session_data:
                session_data['timestamp'] = datetime.now().isoformat()

            history.insert(0, session_data)  # Add to beginning

            # Keep only last 100 sessions
            history = history[:100]

            with open(chat_history_file, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"Error saving chat session: {str(e)}")

    def get_model_performance(self, model_name):
        """Get performance metrics for a model"""
        try:
            # Test model with a simple prompt to measure performance
            import time
            import requests

            test_prompt = "Hello, how are you?"
            start_time = time.time()

            response = requests.post(
                f"http://{self.app.config.get('OLLAMA_HOST')}:{self.app.config.get('OLLAMA_PORT')}/api/generate",
                json={
                    "model": model_name,
                    "prompt": test_prompt,
                    "stream": False
                },
                timeout=30
            )

            end_time = time.time()
            response_time = end_time - start_time

            if response.status_code == 200:
                data = response.json()
                response_text = data.get('response', '')
                eval_count = data.get('eval_count', 0)
                eval_duration = data.get('eval_duration', 0)

                # Calculate tokens per second
                tokens_per_sec = eval_count / (eval_duration / 1e9) if eval_duration > 0 else 0

                return {
                    "model": model_name,
                    "response_time": round(response_time, 2),
                    "tokens_generated": eval_count,
                    "tokens_per_second": round(tokens_per_sec, 2),
                    "response_length": len(response_text),
                    "status": "success"
                }
            else:
                return {
                    "model": model_name,
                    "status": "error",
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

        except Exception as e:
            return {
                "model": model_name,
                "status": "error",
                "error": str(e)
            }

    def get_system_stats_history(self):
        """Get historical system stats"""
        try:
            stats_history_file = os.path.join(os.path.dirname(self.app.config['HISTORY_FILE']), 'system_stats_history.json')

            # Initialize or load existing history
            if os.path.exists(stats_history_file):
                with open(stats_history_file, 'r') as f:
                    history = json.load(f)
            else:
                history = []

            # Add current stats
            current_stats = self.get_system_stats()
            if current_stats:
                current_stats['timestamp'] = datetime.now().isoformat()
                history.append(current_stats)

                # Keep only last 100 entries
                history = history[-100:]

                # Save updated history
                with open(stats_history_file, 'w') as f:
                    json.dump(history, f, indent=2)

            return history

        except Exception as e:
            print(f"Error getting system stats history: {str(e)}")
            return []

    def get_model_info_cached(self, model_name):
        """Get cached model info to avoid repeated API calls"""
        try:
            # Try to get from running models first
            running_models = self.get_running_models()
            for model in running_models:
                if model.get('name') == model_name:
                    return model

            # If not running, check available models
            available_models = self.get_available_models()
            for model in available_models:
                if model.get('name') == model_name:
                    return model

            return None
        except Exception as e:
            print(f"Error getting model info for {model_name}: {str(e)}")
            return None

    def get_service_status(self):
        """Check if Ollama service is running"""
        try:
            import subprocess
            import platform

            if platform.system() == "Windows":
                # On Windows, check if ollama.exe process is running
                try:
                    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ollama.exe', '/NH'],
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        return "ollama.exe" in result.stdout.lower()
                    return False
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    # Try alternative method - check for ollama serve process
                    try:
                        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ollama.exe'],
                                              capture_output=True, text=True, timeout=5)
                        return result.returncode == 0 and "ollama.exe" in result.stdout
                    except Exception:
                        return False
            else:
                # On Unix-like systems, use pgrep or ps
                try:
                    result = subprocess.run(['pgrep', '-f', 'ollama'],
                                          capture_output=True, text=True, timeout=5)
                    return result.returncode == 0
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    # Fallback to ps command
                    try:
                        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
                        return 'ollama' in result.stdout.lower()
                    except Exception:
                        return False

        except Exception as e:
            print(f"Error checking service status: {str(e)}")
            return False

    def start_service(self):
        """Start the Ollama service"""
        try:
            import subprocess
            import platform
            import time
            import os

            # Check if already running
            if self.get_service_status():
                return {"success": True, "message": "Ollama service is already running"}

            if platform.system() == "Windows":
                # On Windows, try multiple methods
                methods_tried = []

                # Method 1: Try Windows service
                try:
                    methods_tried.append("Windows service")
                    result = subprocess.run(['sc', 'start', 'Ollama'],
                                          capture_output=True, text=True, timeout=15)
                    if result.returncode == 0 or "START_PENDING" in result.stdout:
                        time.sleep(5)  # Wait longer for service
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via Windows service"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 2: Try running ollama serve directly
                try:
                    methods_tried.append("direct execution")
                    # Check if ollama command exists
                    ollama_check = subprocess.run(['where', 'ollama'],
                                                capture_output=True, text=True, timeout=5)
                    if ollama_check.returncode == 0:
                        # Start ollama serve in background
                        process = subprocess.Popen(
                            ['ollama', 'serve'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                            close_fds=True
                        )
                        time.sleep(5)  # Wait for startup
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via direct execution"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
                    pass

                # Method 3: Try to find and run from common installation paths
                try:
                    methods_tried.append("installation path")
                    common_paths = [
                        r"C:\Program Files\Ollama\ollama.exe",
                        r"C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe",
                        os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe")
                    ]

                    for path in common_paths:
                        expanded_path = os.path.expandvars(path)
                        if os.path.exists(expanded_path):
                            process = subprocess.Popen(
                                [expanded_path, 'serve'],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                                close_fds=True
                            )
                            time.sleep(5)
                            if self.get_service_status():
                                return {"success": True, "message": f"Ollama service started successfully from {expanded_path}"}
                except (OSError, subprocess.SubprocessError):
                    pass

            else:
                # On Unix-like systems
                methods_tried = []

                # Method 1: Try systemctl (systemd)
                try:
                    methods_tried.append("systemctl")
                    result = subprocess.run(['systemctl', 'start', 'ollama'],
                                          capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        time.sleep(5)
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via systemctl"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 2: Try service command (init.d)
                try:
                    methods_tried.append("service command")
                    result = subprocess.run(['service', 'ollama', 'start'],
                                          capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        time.sleep(5)
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via service command"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 3: Try direct execution
                try:
                    methods_tried.append("direct execution")
                    # Check if ollama command exists
                    ollama_check = subprocess.run(['which', 'ollama'],
                                                capture_output=True, text=True, timeout=5)
                    if ollama_check.returncode == 0:
                        process = subprocess.Popen(
                            ['ollama', 'serve'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            preexec_fn=os.setsid  # Create new process group
                        )
                        time.sleep(5)
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via direct execution"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
                    pass

            # If we get here, all methods failed
            methods_str = ", ".join(methods_tried) if methods_tried else "no methods"
            return {"success": False, "message": f"Failed to start Ollama service. Tried: {methods_str}. Please ensure Ollama is installed and try starting it manually."}

        except Exception as e:
            return {"success": False, "message": f"Unexpected error starting service: {str(e)}"}

    def stop_service(self):
        """Stop the Ollama service"""
        try:
            import subprocess
            import platform
            import time
            import signal
            import os

            # Check if already stopped
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service is already stopped"}

            if platform.system() == "Windows":
                methods_tried = []

                # Method 1: Try Windows service stop
                try:
                    methods_tried.append("Windows service")
                    result = subprocess.run(['sc', 'stop', 'Ollama'],
                                          capture_output=True, text=True, timeout=15)
                    if result.returncode == 0 or "STOP_PENDING" in result.stdout:
                        time.sleep(5)  # Wait for service to stop
                        if not self.get_service_status():
                            return {"success": True, "message": "Ollama service stopped successfully via Windows service"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 2: Try to kill processes gracefully first
                try:
                    methods_tried.append("process termination")
                    # First try graceful termination
                    result = subprocess.run(['taskkill', '/IM', 'ollama.exe'],
                                          capture_output=True, text=True, timeout=10)
                    time.sleep(3)
                    if not self.get_service_status():
                        return {"success": True, "message": "Ollama service stopped successfully via graceful termination"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 3: Force kill if graceful termination didn't work
                try:
                    methods_tried.append("force kill")
                    result = subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'],
                                          capture_output=True, text=True, timeout=10)
                    time.sleep(3)
                    if not self.get_service_status():
                        return {"success": True, "message": "Ollama service stopped successfully via force kill"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

            else:
                methods_tried = []

                # Method 1: Try systemctl (systemd)
                try:
                    methods_tried.append("systemctl")
                    result = subprocess.run(['systemctl', 'stop', 'ollama'],
                                          capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        time.sleep(5)
                        if not self.get_service_status():
                            return {"success": True, "message": "Ollama service stopped successfully via systemctl"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 2: Try service command (init.d)
                try:
                    methods_tried.append("service command")
                    result = subprocess.run(['service', 'ollama', 'stop'],
                                          capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        time.sleep(5)
                        if not self.get_service_status():
                            return {"success": True, "message": "Ollama service stopped successfully via service command"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 3: Try pkill (graceful)
                try:
                    methods_tried.append("pkill graceful")
                    result = subprocess.run(['pkill', '-TERM', '-f', 'ollama'],
                                          capture_output=True, text=True, timeout=10)
                    time.sleep(3)
                    if not self.get_service_status():
                        return {"success": True, "message": "Ollama service stopped successfully via graceful pkill"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 4: Try pkill (force)
                try:
                    methods_tried.append("pkill force")
                    result = subprocess.run(['pkill', '-9', '-f', 'ollama'],
                                          capture_output=True, text=True, timeout=10)
                    time.sleep(3)
                    if not self.get_service_status():
                        return {"success": True, "message": "Ollama service stopped successfully via force pkill"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 5: Try killall as last resort
                try:
                    methods_tried.append("killall")
                    result = subprocess.run(['killall', '-TERM', 'ollama'],
                                          capture_output=True, text=True, timeout=10)
                    time.sleep(3)
                    if not self.get_service_status():
                        return {"success": True, "message": "Ollama service stopped successfully via killall"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

            # If we get here, all methods failed
            methods_str = ", ".join(methods_tried) if methods_tried else "no methods"
            return {"success": False, "message": f"Failed to stop Ollama service. Tried: {methods_str}. The service may not be running or you may need administrative privileges."}

        except Exception as e:
            return {"success": False, "message": f"Unexpected error stopping service: {str(e)}"}

    def restart_service(self):
        """Restart the Ollama service"""
        try:
            stop_result = self.stop_service()
            if not stop_result["success"]:
                return stop_result

            # Wait a moment before starting
            import time
            time.sleep(2)

            start_result = self.start_service()
            if start_result["success"]:
                return {"success": True, "message": "Ollama service restarted successfully"}
            else:
                return start_result

        except Exception as e:
            return {"success": False, "message": f"Unexpected error restarting service: {str(e)}"}

    def get_models_memory_usage(self):
        """Get memory usage information for running models"""
        try:
            # Get running models
            running_models = self.get_running_models()

            # Get system memory info
            system_memory = psutil.virtual_memory()
            system_vram = self._get_vram_info()

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

            # For each running model, estimate memory usage
            # Note: Ollama doesn't provide per-model memory usage directly,
            # so we provide system-level memory info and model size as reference
            for model in running_models:
                model_info = {
                    'name': model['name'],
                    'size': model.get('size', 'Unknown'),
                    'size_bytes': model.get('size_bytes', 0),
                    'estimated_ram_usage': 'N/A',  # Ollama doesn't expose per-model RAM usage
                    'estimated_vram_usage': 'N/A'   # Ollama doesn't expose per-model VRAM usage
                }

                # Try to get model size in bytes for estimation
                try:
                    if model.get('size'):
                        # Parse size string like "4.1 GB" or "2.5 MB"
                        size_str = model['size'].upper()
                        if 'GB' in size_str:
                            size_gb = float(size_str.replace('GB', '').strip())
                            model_info['size_bytes'] = int(size_gb * 1024 * 1024 * 1024)
                        elif 'MB' in size_str:
                            size_mb = float(size_str.replace('MB', '').strip())
                            model_info['size_bytes'] = int(size_mb * 1024 * 1024)
                        elif 'KB' in size_str:
                            size_kb = float(size_str.replace('KB', '').strip())
                            model_info['size_bytes'] = int(size_kb * 1024)
                except Exception:
                    pass

                memory_usage['models'].append(model_info)

            return memory_usage

        except Exception as e:
            print(f"Error getting models memory usage: {str(e)}")
            return {
                'system_ram': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
                'system_vram': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
                'models': [],
                'error': str(e)
            }

    # Duplicate legacy implementations of get_downloadable_models/pull_model removed.
    # Unified versions with category support are defined later in file.

    def load_settings(self):
        """Load settings from file."""
        try:
            if not self.app:
                return self.get_default_settings()

            settings_file = self.app.config.get('SETTINGS_FILE', 'settings.json')
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    return json.load(f)
            return self.get_default_settings()
        except Exception as e:
            print(f"Error loading settings: {e}")
            return self.get_default_settings()

    def save_settings(self, settings):
        """Save settings to file."""
        try:
            if not self.app:
                return False

            settings_file = self.app.config.get('SETTINGS_FILE', 'settings.json')

            # Validate settings
            default_settings = self.get_default_settings()
            clean_settings = {}

            for key, default_value in default_settings.items():
                if key in settings:
                    # Basic type validation
                    if isinstance(default_value, (int, float)) and isinstance(settings[key], (int, float, str)):
                        try:
                            if isinstance(default_value, int):
                                clean_settings[key] = int(settings[key])
                            else:
                                clean_settings[key] = float(settings[key])
                        except ValueError:
                            clean_settings[key] = default_value
                    else:
                        clean_settings[key] = settings[key]
                else:
                    clean_settings[key] = default_value

            with open(settings_file, 'w') as f:
                json.dump(clean_settings, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def get_default_settings(self):
        """Get default model settings."""
        return {
            "temperature": 0.7,
            "top_k": 40,
            "top_p": 0.9,
            "num_ctx": 2048,
            "seed": 0 # 0 means random
        }

    def get_best_models(self):
        """Get a curated list of the best/most popular downloadable models."""
        return [
            {
                "name": "llama3",
                "description": "Meta's latest open LLM",
                "parameter_size": "8B",
                "size": "4.7GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "llama3.1",
                "description": "Meta Llama 3.1 with tool calling",
                "parameter_size": "8B",
                "size": "4.7GB",
                "has_vision": False,
                "has_tools": True,
                "has_reasoning": False
            },
            {
                "name": "mistral",
                "description": "Mistral AI's 7B model",
                "parameter_size": "7B",
                "size": "4.1GB",
                "has_vision": False,
                "has_tools": True,
                "has_reasoning": False
            },
            {
                "name": "gemma",
                "description": "Google's open model",
                "parameter_size": "7B",
                "size": "5.0GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "phi3",
                "description": "Microsoft's lightweight model",
                "parameter_size": "3.8B",
                "size": "2.3GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "neural-chat",
                "description": "Fine-tuned model for chat",
                "parameter_size": "7B",
                "size": "4.1GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "starling-lm",
                "description": "High quality RLHF model",
                "parameter_size": "7B",
                "size": "4.1GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "codellama",
                "description": "Code specialized model",
                "parameter_size": "7B",
                "size": "3.8GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "llama2",
                "description": "Meta's previous generation",
                "parameter_size": "7B",
                "size": "3.8GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "llava",
                "description": "Multimodal (image + text)",
                "parameter_size": "7B",
                "size": "4.5GB",
                "has_vision": True,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "qwen3-vl",
                "description": "Alibaba multimodal + tool-capable model",
                "parameter_size": "4B/8B",
                "size": "3.0GB / 5.5GB",
                "has_vision": True,
                "has_tools": True,
                "has_reasoning": False
            },
            {
                "name": "deepseek-r1",
                "description": "DeepSeek reasoning model (chain-of-thought)",
                "parameter_size": "8B/32B",
                "size": "4.7GB / 19GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": True
            }
        ]

    def get_all_downloadable_models(self):
        """Get extended list of all downloadable models."""
        print("DEBUG: get_all_downloadable_models() called!")
        best = self.get_best_models()
        print(f"DEBUG: best models count = {len(best)}")
        additional = [
            {
                "name": "qwen",
                "description": "Alibaba's multilingual model",
                "parameter_size": "7B",
                "size": "4.5GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "qwen3-vl",
                "description": "Alibaba's multimodal vision model",
                "parameter_size": "4B/8B",
                "size": "3.0GB / 5.5GB",
                "has_vision": True,
                "has_tools": True,
                "has_reasoning": False
            },
            {
                "name": "wizardlm",
                "description": "Instruction-following model",
                "parameter_size": "7B",
                "size": "3.8GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "orca-mini",
                "description": "Small but capable model",
                "parameter_size": "3B",
                "size": "1.9GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "vicuna",
                "description": "Fine-tuned LLaMA model",
                "parameter_size": "7B",
                "size": "3.8GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "nous-hermes",
                "description": "Long context model",
                "parameter_size": "7B",
                "size": "3.8GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "dolphin-mixtral",
                "description": "Uncensored Mixtral variant",
                "parameter_size": "8x7B",
                "size": "26GB",
                "has_vision": False,
                "has_tools": True,
                "has_reasoning": False
            },
            {
                "name": "solar",
                "description": "Upstage's SOLAR model",
                "parameter_size": "10.7B",
                "size": "6.1GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "deepseek-coder",
                "description": "Code-focused model",
                "parameter_size": "6.7B",
                "size": "3.8GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "yi",
                "description": "01.AI's bilingual model",
                "parameter_size": "6B",
                "size": "3.5GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "zephyr",
                "description": "HuggingFace's fine-tuned Mistral",
                "parameter_size": "7B",
                "size": "4.1GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "openchat",
                "description": "OpenChat 3.5 model",
                "parameter_size": "7B",
                "size": "4.1GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "stablelm",
                "description": "Stability AI's language model",
                "parameter_size": "3B",
                "size": "1.6GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "falcon",
                "description": "TII's open-source model",
                "parameter_size": "7B",
                "size": "3.8GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "mixtral",
                "description": "Mistral's MoE model",
                "parameter_size": "8x7B",
                "size": "26GB",
                "has_vision": False,
                "has_tools": True,
                "has_reasoning": False
            },
            {
                "name": "command-r",
                "description": "Cohere's command model",
                "parameter_size": "35B",
                "size": "20GB",
                "has_vision": False,
                "has_tools": True,
                "has_reasoning": False
            },
            {
                "name": "bakllava",
                "description": "Multimodal LLaVA variant",
                "parameter_size": "7B",
                "size": "4.5GB",
                "has_vision": True,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "llava-llama3",
                "description": "LLaVA with Llama 3 base",
                "parameter_size": "8B",
                "size": "5.5GB",
                "has_vision": True,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "llava-phi3",
                "description": "LLaVA with Phi-3 base",
                "parameter_size": "3.8B",
                "size": "2.9GB",
                "has_vision": True,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "moondream",
                "description": "Tiny vision language model",
                "parameter_size": "1.6B",
                "size": "1.7GB",
                "has_vision": True,
                "has_tools": False,
                "has_reasoning": False
            },
            {
                "name": "deepseek-r1",
                "description": "Advanced reasoning model with chain-of-thought",
                "parameter_size": "8B/32B/671B",
                "size": "4.7GB / 19GB / 400GB+",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": True
            },
            {
                "name": "qwq",
                "description": "Qwen with Questions - reasoning specialist",
                "parameter_size": "32B",
                "size": "19GB",
                "has_vision": False,
                "has_tools": False,
                "has_reasoning": True
            }
        ]
        return best + additional

    def get_downloadable_models(self, category='best'):
        """Get downloadable models by category."""
        print(f"DEBUG: get_downloadable_models called with category={category} [VERSION_MARKER_20251123_1440]")
        if category == 'all':
            result = self.get_all_downloadable_models()
            print(f"DEBUG: Returning {len(result)} models")
            return result
        print(f"DEBUG: Returning best models")
        return self.get_best_models()

    def pull_model(self, model_name):
        """Pull a model from the Ollama library."""
        try:
            if self.app:
                host = self.app.config.get('OLLAMA_HOST')
                port = self.app.config.get('OLLAMA_PORT')
            else:
                host = os.getenv('OLLAMA_HOST', 'localhost')
                port = int(os.getenv('OLLAMA_PORT', 11434))

            pull_url = f"http://{host}:{port}/api/pull"

            response = self._session.post(
                pull_url,
                json={"name": model_name, "stream": False},
                timeout=3600
            )

            if response.status_code == 200:
                return {"success": True, "message": f"Model {model_name} pulled successfully"}
            else:
                return {"success": False, "message": f"Failed to pull model: {response.text}"}

        except Exception as e:
            return {"success": False, "message": str(e)}

