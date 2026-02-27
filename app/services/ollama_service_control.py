"""Service control functionality for OllamaService: start, stop, restart, and status checking."""

import os
import platform
import subprocess
import time
from typing import TYPE_CHECKING

import requests

from app.services.service_control import stop_service_unix, stop_service_windows

if TYPE_CHECKING:
    import logging
    import threading
    from requests import Session


class OllamaServiceControl:
    """Service control functionality for OllamaService.

    Note: This mixin expects the following attributes/methods from OllamaServiceCore:
    - self.logger, self._session, self._get_ollama_host_port(),
    - self._background_stats, self._stop_background, self.clear_all_caches(),
    - self._start_background_updates(), self.get_component_health()
    And from OllamaServiceUtilities:
    - self.load_model_settings()
    """
    # pylint: disable=no-member

    if TYPE_CHECKING:
        logger: logging.Logger
        _session: Session
        _background_stats: threading.Thread
        _stop_background: threading.Event
        _model_settings: dict
        def _get_ollama_host_port(self) -> tuple[str, int]:
            """Return (host, port) for Ollama API. Must be implemented in subclass."""
            # Example default, override in subclass as needed
            return ("localhost", 11434)
        def _start_background_updates(self) -> None:
            """Start background updates thread."""
        def load_model_settings(self) -> dict:
            """Load model settings from disk."""
        def clear_all_caches(self) -> None:
            """Clear all cached data."""
        def get_component_health(self) -> dict:
            """Get component health status."""

    def _start_service_windows(self):
        """Attempt to start Ollama service on Windows using several strategies.
        Returns (result_dict, methods_tried). result_dict is None if not successful yet.
        """
        methods_tried = []
        if platform.system() != 'Windows':
            return None, methods_tried
        # Method 1: Windows service
        try:
            methods_tried.append('Windows service')
            result = subprocess.run(['sc', 'start', 'Ollama'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0 or 'START_PENDING' in result.stdout:
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via Windows service"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # Method 2: common installation paths (prioritized over where ollama - more reliable)
        try:
            methods_tried.append('installation path')
            common_paths = [
                r"C:\Program Files\Ollama\ollama.exe",
                r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
                r"C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe")
            ]
            for path in common_paths:
                expanded = os.path.expandvars(os.path.expanduser(path))
                if os.path.exists(expanded):
                    try:
                        subprocess.Popen(
                            [expanded, 'serve'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                            close_fds=True,
                            cwd=os.path.dirname(expanded)
                        )
                    except Exception as e:
                        self.logger.debug("Popen failed for %s: %s", expanded, e)
                    time.sleep(5)
                    if self.get_service_status():
                        return {"success": True, "message": f"Ollama service started successfully from {expanded}"}, methods_tried
                    # API fallback: process may be slow to appear in tasklist
                    try:
                        api_ok, _ = self._verify_ollama_api(max_retries=2, retry_delay=1)
                        if api_ok:
                            return {"success": True, "message": f"Ollama service started successfully from {expanded}"}, methods_tried
                    except Exception:
                        pass
        except (OSError, subprocess.SubprocessError):
            pass
        # Method 3: direct execution if command exists
        try:
            methods_tried.append('direct execution')
            check = subprocess.run(['where', 'ollama'], capture_output=True, text=True, timeout=5, check=False)
            if check.returncode == 0:
                try:
                    subprocess.Popen(
                        ['ollama', 'serve'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                        close_fds=True
                    )
                except Exception as e:
                    self.logger.debug("Popen failed for ollama serve: %s", e)
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via direct execution"}, methods_tried
                try:
                    api_ok, _ = self._verify_ollama_api(max_retries=2, retry_delay=1)
                    if api_ok:
                        return {"success": True, "message": "Ollama service started successfully via direct execution"}, methods_tried
                except Exception:
                    pass
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass
        return None, methods_tried

    def _start_service_unix(self):
        """Attempt to start Ollama service on Unix-like systems. Returns (result_dict, methods_tried)."""
        methods_tried = []
        if platform.system() == 'Windows':
            return None, methods_tried
        # systemctl
        try:
            methods_tried.append('systemctl')
            result = subprocess.run(['systemctl', 'start', 'ollama'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0:
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via systemctl"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # service command
        try:
            methods_tried.append('service command')
            result = subprocess.run(['service', 'ollama', 'start'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0:
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via service command"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # direct execution
        try:
            methods_tried.append('direct execution')
            check = subprocess.run(['which', 'ollama'], capture_output=True, text=True, timeout=5, check=False)
            if check.returncode == 0:
                try:
                    subprocess.Popen(
                        ['ollama', 'serve'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                except Exception:
                    pass
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via direct execution"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass
        return None, methods_tried

    def _stop_service_windows(self):
        """Attempt to stop service on Windows. Returns (result_dict, methods_tried)."""
        methods_tried = []
        if platform.system() != 'Windows':
            return None, methods_tried
        # Windows service stop
        try:
            methods_tried.append('Windows service')
            result = subprocess.run(['sc', 'stop', 'Ollama'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0 or 'STOP_PENDING' in result.stdout:
                time.sleep(5)
                if not self.get_service_status():
                    return {"success": True, "message": "Ollama service stopped successfully via Windows service"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # Graceful termination
        try:
            methods_tried.append('process termination')
            subprocess.run(['taskkill', '/IM', 'ollama.exe'], capture_output=True, text=True, timeout=10, check=False)
            time.sleep(5)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via graceful termination"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # Force kill
        try:
            methods_tried.append('force kill')
            subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], capture_output=True, text=True, timeout=10, check=False)
            time.sleep(5)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via force kill"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        return None, methods_tried

    def _stop_service_unix(self):
        """Attempt to stop service on Unix-like systems. Returns (result_dict, methods_tried)."""
        methods_tried = []
        if platform.system() == 'Windows':
            return None, methods_tried
        # systemctl
        try:
            methods_tried.append('systemctl')
            result = subprocess.run(['systemctl', 'stop', 'ollama'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0:
                time.sleep(5)
                if not self.get_service_status():
                    return {"success": True, "message": "Ollama service stopped successfully via systemctl"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # service command
        try:
            methods_tried.append('service command')
            result = subprocess.run(['service', 'ollama', 'stop'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0:
                time.sleep(5)
                if not self.get_service_status():
                    return {"success": True, "message": "Ollama service stopped successfully via service command"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # pkill TERM
        try:
            methods_tried.append('pkill graceful')
            subprocess.run(['pkill', '-TERM', '-f', 'ollama'], capture_output=True, text=True, timeout=10, check=False)
            time.sleep(3)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via graceful pkill"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # pkill -9
        try:
            methods_tried.append('pkill force')
            subprocess.run(['pkill', '-9', '-f', 'ollama'], capture_output=True, text=True, timeout=10, check=False)
            time.sleep(3)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via force pkill"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # killall TERM
        try:
            methods_tried.append('killall')
            subprocess.run(['killall', '-TERM', 'ollama'], capture_output=True, text=True, timeout=10, check=False)
            time.sleep(3)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via killall"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        return None, methods_tried

    def _verify_ollama_api(self, max_retries=5, retry_delay=2):
        """Verify Ollama API is accessible with retry logic."""
        try:
            host_port = self._get_ollama_host_port()
            if isinstance(host_port, (tuple, list)) and len(host_port) == 2:
                host, port = host_port
            elif isinstance(host_port, str):
                # If a string is returned, try to split by ':' (host:port)
                host_port_str = str(host_port)
                if ':' in host_port_str:
                    host, port_str = host_port_str.split(':', 1)
                    port = int(port_str)
                else:
                    raise ValueError("_get_ollama_host_port() must return (host, port) or 'host:port' string")
            else:
                raise ValueError("_get_ollama_host_port() must return (host, port)")
            test_url = f"http://{host}:{port}/api/tags"
        except Exception as e:
            return False, f"Error constructing API URL: {str(e)}"

        for attempt in range(max_retries):
            try:
                response = self._session.get(test_url, timeout=3)
                if response.status_code == 200:
                    return True, "API is accessible"
                elif response.status_code in (404, 405):
                    # API endpoint exists but wrong method - service is running
                    return True, "Service is running (API endpoint exists)"
                else:
                    return False, f"API returned status {response.status_code}"
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False, f"Cannot connect to Ollama API: {str(e)[:100]}"
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False, "API connection timed out"
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False, f"API verification error: {str(e)[:100]}"

        return False, "API verification failed after retries"

    def get_service_status(self) -> bool:
        """Check if Ollama service is running."""
        try:
            if platform.system() == "Windows":
                # On Windows, check if ollama.exe process is running
                try:
                    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ollama.exe', '/NH'],
                        capture_output=True, text=True, timeout=5, check=False)
                    if result.returncode == 0 and result.stdout:
                        return "ollama.exe" in result.stdout.lower()
                    return False
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
                    self.logger.debug("Tasklist check failed: %s", e)
                    # Try alternative method - check for ollama serve process
                    try:
                        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ollama.exe'],
                            capture_output=True, text=True, timeout=5, check=False)
                        if result.returncode == 0 and result.stdout:
                            return "ollama.exe" in result.stdout
                        return False
                    except Exception as e2:
                        self.logger.debug("Alternative tasklist check failed: %s", e2)
                        return False
            else:
                # On Unix-like systems, use pgrep or ps
                try:
                    result = subprocess.run(['pgrep', '-f', 'ollama'],
                        capture_output=True, text=True, timeout=5, check=False)
                    return result.returncode == 0
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
                    self.logger.debug("Pgrep check failed: %s", e)
                    # Fallback to ps command
                    try:
                        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5, check=False)
                        if result.returncode == 0 and result.stdout:
                            return 'ollama' in result.stdout.lower()
                        return False
                    except Exception as e2:
                        self.logger.debug("Ps check failed: %s", e2)
                        return False

        except Exception as e:
            self.logger.exception("Error checking service status: %s", e)
            return False

        # Fallback to False if no earlier branch returned
        return False

    def start_service(self):
        """Start the Ollama service"""
        try:
            # Check if already running (with error handling)
            is_running = False
            try:
                is_running = self.get_service_status()
            except Exception as e:
                self.logger.warning("Error checking service status: %s", e)
                # Assume not running if check fails
                is_running = False

            if is_running:
                # Verify API is accessible
                try:
                    api_ok, api_msg = self._verify_ollama_api(max_retries=3, retry_delay=1)
                    if api_ok:
                        return {"success": True, "message": "Ollama service is already running and API is accessible"}
                    else:
                        return {"success": False, "message": f"Ollama process is running but API is not accessible: {api_msg}. Try restarting the service."}
                except Exception as e:
                    self.logger.warning("Error verifying API: %s", e)
                    return {"success": True, "message": "Ollama service appears to be running (API verification failed)"}

            if platform.system() == "Windows":
                # On Windows, try multiple methods
                methods_tried = []

                # Method 1: Try Windows service
                try:
                    methods_tried.append("Windows service")
                    result = subprocess.run(['sc', 'start', 'Ollama'],
                        capture_output=True, text=True, timeout=15, check=False)
                    if result.returncode == 0 or "START_PENDING" in result.stdout:
                        time.sleep(5)  # Wait longer for service
                        if self.get_service_status():
                            # Verify API is accessible
                            try:
                                api_ok, api_msg = self._verify_ollama_api(max_retries=3, retry_delay=2)
                                if api_ok:
                                    return {"success": True, "message": "Ollama service started successfully via Windows service"}
                                else:
                                    return {"success": False, "message": f"Service started but API not accessible: {api_msg}"}
                            except Exception as e:
                                self.logger.warning("API verification error: %s", e)
                                return {"success": True, "message": "Ollama service started via Windows service (API verification failed)"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 2: Try to find and run from common installation paths (prioritized - more reliable)
                try:
                    methods_tried.append("installation path")
                    common_paths = [
                        r"C:\Program Files\Ollama\ollama.exe",
                        r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
                        r"C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe",
                        os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe")
                    ]

                    for path in common_paths:
                        expanded_path = os.path.expandvars(os.path.expanduser(path))
                        if os.path.exists(expanded_path):
                            try:
                                subprocess.Popen(
                                    [expanded_path, 'serve'],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                                    close_fds=True,
                                    cwd=os.path.dirname(expanded_path)
                                )
                            except Exception as e:
                                self.logger.debug("Popen failed for %s: %s", expanded_path, e)
                            time.sleep(5)
                            if self.get_service_status():
                                # Verify API is accessible
                                try:
                                    api_ok, api_msg = self._verify_ollama_api(max_retries=3, retry_delay=2)
                                    if api_ok:
                                        return {"success": True, "message": f"Ollama service started successfully from {expanded_path}"}
                                    else:
                                        return {"success": False, "message": f"Service started but API not accessible: {api_msg}"}
                                except Exception as e:
                                    self.logger.warning("API verification error: %s", e)
                                    return {"success": True, "message": f"Ollama service started from {expanded_path} (API verification failed)"}
                            # API fallback: process may be slow to appear in tasklist
                            try:
                                api_ok, api_msg = self._verify_ollama_api(max_retries=2, retry_delay=1)
                                if api_ok:
                                    return {"success": True, "message": f"Ollama service started successfully from {expanded_path}"}
                            except Exception:
                                pass
                except (OSError, subprocess.SubprocessError):
                    pass

                # Method 3: Try running ollama serve directly
                try:
                    methods_tried.append("direct execution")
                    # Check if ollama command exists
                    ollama_check = subprocess.run(['where', 'ollama'],
                        capture_output=True, text=True, timeout=5, check=False)
                    if ollama_check.returncode == 0:
                        # Start ollama serve in background
                        try:
                            subprocess.Popen(
                                ['ollama', 'serve'],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                                close_fds=True
                            )
                        except Exception as e:
                            self.logger.debug("Popen failed for ollama serve: %s", e)
                        time.sleep(5)  # Wait for startup
                        if self.get_service_status():
                            # Verify API is accessible
                            try:
                                api_ok, api_msg = self._verify_ollama_api(max_retries=3, retry_delay=2)
                                if api_ok:
                                    return {"success": True, "message": "Ollama service started successfully via direct execution"}
                                else:
                                    return {"success": False, "message": f"Service started but API not accessible: {api_msg}"}
                            except Exception as e:
                                self.logger.warning("API verification error: %s", e)
                                return {"success": True, "message": "Ollama service started via direct execution (API verification failed)"}
                        # API fallback
                        try:
                            api_ok, api_msg = self._verify_ollama_api(max_retries=2, retry_delay=1)
                            if api_ok:
                                return {"success": True, "message": "Ollama service started successfully via direct execution"}
                        except Exception:
                            pass
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
                    pass

            else:
                # On Unix-like systems
                methods_tried = []

                # Method 1: Try systemctl (systemd)
                try:
                    methods_tried.append("systemctl")
                    result = subprocess.run(['systemctl', 'start', 'ollama'],
                        capture_output=True, text=True, timeout=15, check=False)
                    if result.returncode == 0:
                        time.sleep(5)
                        if self.get_service_status():
                            # Verify API is accessible
                            try:
                                api_ok, api_msg = self._verify_ollama_api(max_retries=3, retry_delay=2)
                                if api_ok:
                                    return {"success": True, "message": "Ollama service started successfully via systemctl"}
                                else:
                                    return {"success": False, "message": f"Service started but API not accessible: {api_msg}"}
                            except Exception as e:
                                self.logger.warning("API verification error: %s", e)
                                return {"success": True, "message": "Ollama service started via systemctl (API verification failed)"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 2: Try service command (init.d)
                try:
                    methods_tried.append("service command")
                    result = subprocess.run(['service', 'ollama', 'start'],
                        capture_output=True, text=True, timeout=15, check=False)
                    if result.returncode == 0:
                        time.sleep(5)
                        if self.get_service_status():
                            # Verify API is accessible
                            try:
                                api_ok, api_msg = self._verify_ollama_api(max_retries=3, retry_delay=2)
                                if api_ok:
                                    return {"success": True, "message": "Ollama service started successfully via service command"}
                                else:
                                    return {"success": False, "message": f"Service started but API not accessible: {api_msg}"}
                            except Exception as e:
                                self.logger.warning("API verification error: %s", e)
                                return {"success": True, "message": "Ollama service started via service command (API verification failed)"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 3: Try direct execution
                try:
                    methods_tried.append("direct execution")
                    # Check if ollama command exists
                    ollama_check = subprocess.run(['which', 'ollama'],
                                                capture_output=True, text=True, timeout=5, check=False)
                    if ollama_check.returncode == 0:
                        subprocess.Popen(
                            ['ollama', 'serve'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True  # Safer than preexec_fn in threaded apps
                        )
                        time.sleep(5)
                        if self.get_service_status():
                            # Verify API is accessible
                            try:
                                api_ok, api_msg = self._verify_ollama_api(max_retries=3, retry_delay=2)
                                if api_ok:
                                    return {"success": True, "message": "Ollama service started successfully via direct execution"}
                                else:
                                    return {"success": False, "message": f"Service started but API not accessible: {api_msg}"}
                            except Exception as e:
                                self.logger.warning("API verification error: %s", e)
                                return {"success": True, "message": "Ollama service started via direct execution (API verification failed)"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
                    pass

            # If we get here, all methods failed
            methods_str = ", ".join(methods_tried) if methods_tried else "no methods"
            return {"success": False, "message": f"Failed to start Ollama service. Tried: {methods_str}. Please ensure Ollama is installed and try starting it manually."}

        except Exception as e:
            return {"success": False, "message": f"Unexpected error starting service: {str(e)}"}

    def stop_service(self):
        """Stop the Ollama service."""
        try:
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service is already stopped"}
            if platform.system() == 'Windows':
                result, methods = stop_service_windows(self.get_service_status)
            else:
                result, methods = stop_service_unix(self.get_service_status)
            if result:
                return result
            methods_str = ", ".join(methods) if methods else "no methods"
            return {"success": False, "message": f"Failed to stop Ollama service. Tried: {methods_str}."}
        except Exception as e:
            return {"success": False, "message": f"Unexpected error stopping service: {str(e)}"}

    def restart_service(self):
        """Restart the Ollama service."""
        try:
            # Stop background updates temporarily to avoid race conditions during restart
            try:
                if self._background_stats and self._background_stats.is_alive():
                    self._stop_background.set()
                    self._background_stats.join(timeout=5)
            except Exception:
                pass
            stop_result = self.stop_service()
            # Poll until service is down (up to 10s); do not return early on stop "failure"
            # - stop may report failure (e.g. sc stop fails) yet taskkill succeeded
            for _ in range(10):
                if not self.get_service_status():
                    break
                time.sleep(1)
            else:
                # Service still running after poll - hard failure
                return stop_result if not stop_result["success"] else {
                    "success": False,
                    "message": "Ollama service could not be stopped (still running after stop attempts)."
                }

            time.sleep(10)  # Allow port 11434 to be released before starting

            start_result = self.start_service()
            if start_result["success"]:
                # Flush caches and restart background thread
                try:
                    if hasattr(self, "clear_all_caches") and callable(getattr(self, "clear_all_caches", None)):
                        if hasattr(self, "clear_all_caches") and callable(getattr(self, "clear_all_caches", None)):
                            self.clear_all_caches()
                except AttributeError:
                    self.logger.warning("clear_all_caches method not found on OllamaServiceControl instance")
                except Exception:
                    pass
                try:
                    self._stop_background.clear()
                    self._start_background_updates()
                except Exception:
                    pass
                return {"success": True, "message": "Ollama service restarted successfully (caches & background refreshed)"}
            else:
                # Attempt to restart background updates even on failure to avoid stale thread state
                try:
                    self._stop_background.clear()
                    self._start_background_updates()
                except Exception:
                    pass
                return start_result

        except Exception as e:
            return {"success": False, "message": f"Unexpected error restarting service: {str(e)}"}

    def full_restart(self):
        """Comprehensive application restart: clear caches, reload model settings, restart background thread, return health. Does NOT restart Ollama service."""
        try:
            # Stop background thread first
            try:
                if self._background_stats and self._background_stats.is_alive():
                    self._stop_background.set()
                    self._background_stats.join(timeout=3)
            except Exception:
                pass

            # Clear all caches and reset error states
            try:
                if hasattr(self, "clear_all_caches") and callable(getattr(self, "clear_all_caches", None)):
                    self.clear_all_caches()
            except Exception:
                pass
            # Reload model settings to pick up external changes
            try:
                if hasattr(self, 'load_model_settings') and callable(getattr(self, 'load_model_settings', None)):
                    self.load_model_settings()
            except (AttributeError, OSError, ValueError):
                pass


            # Restart background thread
            try:
                self._stop_background.clear()
                self._start_background_updates()
            except (AttributeError, RuntimeError):
                pass

            return {"success": True, "message": "Full application restart completed", "health": self.get_component_health()}
        except (AttributeError, RuntimeError, OSError) as e:
            return {"success": False, "message": f"Unexpected error performing full restart: {str(e)}"}
