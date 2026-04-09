"""Service control functionality for OllamaService: start, stop, restart, and status checking."""
# pylint: disable=broad-exception-caught,line-too-long  # intentional: must not crash on any error; long messages

import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Optional, Tuple

import requests

from app.services.service_control import stop_service_unix, stop_service_windows

# Resolves to GitHub latest OllamaSetup.exe (same as https://ollama.com/download/windows).
OLLAMA_WINDOWS_SETUP_EXE_URL = "https://ollama.com/download/OllamaSetup.exe"

_WINGET_FALLBACK_PATHS = (r"%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe",)
_CHOCO_FALLBACK_PATHS = (
    r"%ChocolateyInstall%\bin\choco.exe",
    r"%ProgramData%\chocolatey\bin\choco.exe",
)
# Appended to install/update API errors on Windows so responses are identifiable vs. legacy builds.
WINDOWS_UPDATE_FAILURE_TAG = " [win-upd:setup-exe]"
_CURL_FALLBACK_PATHS = (r"%SystemRoot%\System32\curl.exe",)


def _windows_resolve_exe(name: str, *extra_paths: str) -> Optional[str]:
    """Find an executable: PATH first, then well-known install locations (service / non-login PATH)."""
    found = shutil.which(name)
    if found:
        return found
    for tmpl in extra_paths:
        path = os.path.expandvars(tmpl)
        if path and os.path.isfile(path):
            return path
    return None


def _windows_powershell_exe() -> Optional[str]:
    for candidate in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
        found = shutil.which(candidate)
        if found:
            return found
    return _windows_resolve_exe(
        "powershell.exe",
        r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe",
    )


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
                r"C:\Program Files (x86)\Ollama\ollama.exe",
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

    def _force_kill_ollama_process(self):
        """Force-kill any Ollama process (Windows: taskkill /F, Unix: pkill -9). No graceful stop."""
        try:
            if platform.system() == 'Windows':
                subprocess.run(
                    ['taskkill', '/F', '/IM', 'ollama.exe'],
                    capture_output=True, text=True, timeout=10, check=False
                )
            else:
                subprocess.run(
                    ['pkill', '-9', '-f', 'ollama'],
                    capture_output=True, text=True, timeout=10, check=False
                )
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass

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

    def is_ollama_installed(self) -> bool:
        """True if the Ollama CLI/binary is present (not whether the service is running)."""
        try:
            if platform.system() == "Windows":
                common_paths = [
                    r"C:\Program Files\Ollama\ollama.exe",
                    r"C:\Program Files (x86)\Ollama\ollama.exe",
                    r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
                    r"C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe",
                    os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
                ]
                for path in common_paths:
                    expanded = os.path.expandvars(os.path.expanduser(path))
                    if expanded and os.path.isfile(expanded):
                        return True
                # PATHEXT + process PATH (often finds Ollama when `where` fails in restricted contexts)
                try:
                    which_ollama = shutil.which("ollama")
                    if which_ollama and os.path.isfile(which_ollama):
                        return True
                except (OSError, TypeError):
                    pass
                try:
                    result = subprocess.run(
                        ["where", "ollama"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    if result.returncode == 0 and (result.stdout or "").strip():
                        return True
                except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                    pass
                return False
            try:
                result = subprocess.run(
                    ["which", "ollama"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                if result.returncode == 0 and (result.stdout or "").strip():
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass
            for path in (
                "/usr/local/bin/ollama",
                "/usr/bin/ollama",
                os.path.expanduser("~/.local/bin/ollama"),
            ):
                if path and os.path.isfile(path) and os.access(path, os.X_OK):
                    return True
            return False
        except Exception:
            self.logger.debug("is_ollama_installed check failed", exc_info=True)
            return False

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
                    # Process running but API not accessible: force kill and start fresh
                    self.logger.info("Ollama process running but API not accessible; force-killing and starting")
                    self._force_kill_ollama_process()
                    for _ in range(15):
                        if not self.get_service_status():
                            break
                        time.sleep(1)
                    time.sleep(2)  # Allow port to be released
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
        """Restart the Ollama service: force-kill completely first, then start."""
        try:
            # Stop background updates temporarily to avoid race conditions during restart
            try:
                if self._background_stats and self._background_stats.is_alive():
                    self._stop_background.set()
                    self._background_stats.join(timeout=5)
            except Exception:
                pass
            # Force-kill first so the process is completely gone before starting
            self._force_kill_ollama_process()
            time.sleep(2)
            for _ in range(15):
                if not self.get_service_status():
                    break
                time.sleep(1)
            # If still running, try full stop (sc stop + taskkill / pkill)
            if self.get_service_status():
                self.stop_service()
                for _ in range(10):
                    if not self.get_service_status():
                        break
                    time.sleep(1)
            if self.get_service_status():
                return {"success": False, "message": "Ollama service could not be stopped (still running after force kill)."}
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

    def _download_ollama_setup_exe(self, path: str) -> Tuple[bool, str]:
        """Download latest OllamaSetup.exe: requests, urllib, curl.exe, then PowerShell."""
        headers = {"User-Agent": "ollama-dashboard/Windows-Ollama-setup"}
        resp = None
        try:
            resp = requests.get(
                OLLAMA_WINDOWS_SETUP_EXE_URL,
                headers=headers,
                stream=True,
                timeout=(30, 600),
                allow_redirects=True,
            )
            resp.raise_for_status()
            with open(path, "wb") as out:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)
            return True, ""
        except requests.RequestException as exc:
            self.logger.warning("OllamaSetup download via requests failed: %s", exc)
        finally:
            if resp is not None:
                try:
                    resp.close()
                except OSError:
                    pass

        try:
            req = urllib.request.Request(OLLAMA_WINDOWS_SETUP_EXE_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=600) as url_resp:
                with open(path, "wb") as out:
                    shutil.copyfileobj(url_resp, out, length=1024 * 1024)
            return True, ""
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            self.logger.warning("OllamaSetup download via urllib failed: %s", exc)

        curl = _windows_resolve_exe("curl", *_CURL_FALLBACK_PATHS)
        if curl:
            try:
                proc = subprocess.run(
                    [
                        curl,
                        "-fSL",
                        "--retry",
                        "2",
                        "-o",
                        path,
                        OLLAMA_WINDOWS_SETUP_EXE_URL,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return False, "curl download timed out (over 10 minutes)."
            if proc.returncode == 0:
                return True, ""
            tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-500:]
            return False, f"curl could not download installer (exit {proc.returncode}). {tail}"

        ps = _windows_powershell_exe()
        if ps:
            cmdline = (
                f"Invoke-WebRequest -Uri {json.dumps(OLLAMA_WINDOWS_SETUP_EXE_URL)} "
                f"-OutFile {json.dumps(path)} -UseBasicParsing"
            )
            try:
                proc = subprocess.run(
                    [
                        ps,
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        cmdline,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return False, "PowerShell download timed out (over 10 minutes)."
            if proc.returncode == 0:
                return True, ""
            tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-500:]
            return False, f"PowerShell could not download installer (exit {proc.returncode}). {tail}"

        return False, (
            f"Could not download installer ({OLLAMA_WINDOWS_SETUP_EXE_URL}). "
            "Install manually from https://ollama.com/download/windows"
        )

    def _windows_install_via_official_setup(self) -> Tuple[bool, str]:
        """Download OllamaSetup.exe and run a silent install or in-place upgrade (Inno Setup).

        Used when winget / Chocolatey are missing or fail. See Ollama Windows docs for /DIR etc.
        """
        path: Optional[str] = None
        try:
            try:
                fd, path = tempfile.mkstemp(suffix=".exe")
                os.close(fd)
            except OSError as exc:
                return False, f"Could not create temp file for installer: {exc}"

            ok_dl, dl_err = self._download_ollama_setup_exe(path)
            if not ok_dl:
                return False, dl_err

            try:
                size = os.path.getsize(path)
            except OSError as exc:
                return False, f"Downloaded installer missing or unreadable: {exc}"
            if size < 1_000_000:
                return (
                    False,
                    f"Downloaded file too small ({size} bytes); expected OllamaSetup.exe. "
                    "Install manually from https://ollama.com/download/windows",
                )

            try:
                proc = subprocess.run(
                    [path, "/SP-", "/VERYSILENT", "/NORESTART"],
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return False, "Official Windows installer timed out (over 15 minutes)."
            combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            if proc.returncode == 0:
                return True, combined or "Ollama updated via official Windows installer."
            tail = combined[-800:] if combined else "No output."
            return (
                False,
                f"Official installer exited with code {proc.returncode}. {tail} "
                "You can install manually from https://ollama.com/download/windows",
            )
        finally:
            if path:
                try:
                    if os.path.isfile(path):
                        os.unlink(path)
                except OSError:
                    self.logger.warning("Could not remove temp installer at %s", path)

    def _run_ollama_upgrade(self) -> Tuple[bool, str]:
        """Run platform-specific Ollama upgrade (service must be stopped). Returns (ok, detail)."""
        system = platform.system()
        if system == "Windows":
            return self._upgrade_ollama_windows()
        if system == "Darwin":
            return self._upgrade_ollama_darwin()
        return self._upgrade_ollama_linux()

    def _upgrade_ollama_windows(self) -> Tuple[bool, str]:
        winget_err: Optional[str] = None
        winget = _windows_resolve_exe("winget", *_WINGET_FALLBACK_PATHS)
        if winget:
            proc = None
            try:
                proc = subprocess.run(
                    [
                        winget,
                        "upgrade",
                        "-e",
                        "--id",
                        "Ollama.Ollama",
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                        "--silent",
                        "--disable-interactivity",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                winget_err = "winget upgrade timed out (over 15 minutes)."
            if proc is not None:
                combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
                low = combined.lower()
                if proc.returncode == 0:
                    return True, combined or "Ollama upgraded via winget."
                if any(
                    phrase in low
                    for phrase in (
                        "no newer package",
                        "no applicable upgrade",
                        "no updates found",
                        "already installed",
                        "is already installed",
                        "a newer version was not found",
                        "successfully installed",
                        "successfully upgraded",
                        "no available upgrade",
                        "up to date",
                        "install technology not supported",
                    )
                ):
                    return True, "Ollama is already up to date (winget)."
                if proc.returncode in (
                    -1978335189,  # 0x8A15006B - UPDATE_NOT_APPLICABLE
                    -1978335135,  # 0x8A1500A1 - REBOOT_REQUIRED_TO_INSTALL
                    3010,         # ERROR_SUCCESS_REBOOT_REQUIRED
                ):
                    return True, "Ollama upgraded via winget (reboot may be recommended)."
                self.logger.warning("winget upgrade exit %d: %s", proc.returncode, combined[-2000:])
                winget_err = (combined or f"winget exit {proc.returncode}")[-1500:]

        choco_err: Optional[str] = None
        choco = _windows_resolve_exe("choco", *_CHOCO_FALLBACK_PATHS)
        if choco:
            cproc = None
            try:
                cproc = subprocess.run(
                    [choco, "upgrade", "ollama", "-y"],
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                choco_err = "Chocolatey upgrade timed out (over 15 minutes)."
            if cproc is not None:
                combined = ((cproc.stdout or "") + "\n" + (cproc.stderr or "")).strip()
                low = combined.lower()
                if cproc.returncode == 0:
                    return True, combined or "Ollama upgraded via Chocolatey."
                if "already installed" in low or "nothing to do" in low or "up to date" in low:
                    return True, "Ollama is already up to date (Chocolatey)."
                self.logger.warning("choco upgrade exit %d: %s", cproc.returncode, combined[-2000:])
                choco_err = f"Chocolatey failed (exit {cproc.returncode}). {combined[-800:]}"

        ok_setup, setup_msg = self._windows_install_via_official_setup()
        if ok_setup:
            return True, setup_msg
        ctx: list[str] = []
        if winget_err:
            ctx.append(f"winget: {winget_err[:400]}")
        if choco_err:
            ctx.append(choco_err[:500])
        if ctx:
            return False, f"{setup_msg} Context: {' | '.join(ctx)}"
        return False, setup_msg

    def _upgrade_ollama_darwin(self) -> Tuple[bool, str]:
        brew = shutil.which("brew")
        if not brew:
            return False, "Homebrew not found. Update from https://ollama.com/download/mac"
        for args in (["upgrade", "--cask", "ollama"], ["upgrade", "ollama"]):
            try:
                proc = subprocess.run(
                    [brew] + args,
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return False, "brew upgrade timed out (over 15 minutes)."
            combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            low = combined.lower()
            if proc.returncode == 0:
                return True, combined or "Ollama upgraded via Homebrew."
            if "already up-to-date" in low or "already installed" in low:
                return True, "Ollama is already up to date (Homebrew)."
        return False, f"brew upgrade failed: {combined[-800:]}"

    def _upgrade_ollama_linux(self) -> Tuple[bool, str]:
        try:
            proc = subprocess.run(
                ["/bin/sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "Install script timed out (over 15 minutes)."
        combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if proc.returncode == 0:
            return True, combined or "Ollama updated via official install script."
        return False, f"Install script failed (exit {proc.returncode}). {combined[-800:]}"

    def update_ollama(self):
        """Stop Ollama, run platform upgrade, then start the service again."""
        try:
            try:
                if self._background_stats and self._background_stats.is_alive():
                    self._stop_background.set()
                    self._background_stats.join(timeout=5)
            except Exception:
                pass

            if self.get_service_status():
                self._force_kill_ollama_process()
                time.sleep(2)
                for _ in range(15):
                    if not self.get_service_status():
                        break
                    time.sleep(1)
                if self.get_service_status():
                    self.stop_service()
                    for _ in range(10):
                        if not self.get_service_status():
                            break
                        time.sleep(1)
                if self.get_service_status():
                    try:
                        self._stop_background.clear()
                        self._start_background_updates()
                    except Exception:
                        pass
                    return {"success": False, "message": "Ollama could not be stopped before update."}
                time.sleep(10)

            ok, upgrade_msg = self._run_ollama_upgrade()
            start_result = self.start_service()

            try:
                if hasattr(self, "clear_all_caches") and callable(getattr(self, "clear_all_caches", None)):
                    self.clear_all_caches()
            except Exception:
                pass
            try:
                self._stop_background.clear()
                self._start_background_updates()
            except Exception:
                pass

            if start_result.get("success"):
                api_ok, _ = self._verify_ollama_api(max_retries=5, retry_delay=2)
                if api_ok:
                    if not ok:
                        self.logger.warning(
                            "Upgrade tool reported failure (%s) but Ollama is running; treating as success.",
                            upgrade_msg,
                        )
                    return {
                        "success": True,
                        "message": f"Ollama updated and running.{'' if ok else ' (package manager reported a warning but the service is healthy)'}",
                    }

            if not ok:
                tag = WINDOWS_UPDATE_FAILURE_TAG if platform.system() == "Windows" else ""
                msg = f"Update step failed: {upgrade_msg}{tag}"
                if start_result.get("success"):
                    return {"success": False, "message": f"{msg} Ollama was started again but API is not responding."}
                return {
                    "success": False,
                    "message": f"{msg} Could not restart Ollama: {start_result.get('message', 'unknown')}.",
                }

            return {
                "success": False,
                "message": f"Update completed but Ollama failed to start: {start_result.get('message')}. {upgrade_msg}",
            }
        except Exception as e:
            try:
                self._stop_background.clear()
                self._start_background_updates()
            except Exception:
                pass
            return {"success": False, "message": f"Unexpected error during Ollama update: {str(e)}"}

    def _run_ollama_install(self) -> Tuple[bool, str]:
        """Run platform-specific first-time install. Returns (ok, detail)."""
        system = platform.system()
        if system == "Windows":
            return self._install_ollama_windows()
        if system == "Darwin":
            return self._install_ollama_darwin()
        return self._install_ollama_linux()

    def _install_ollama_windows(self) -> Tuple[bool, str]:
        winget_err: Optional[str] = None
        winget = _windows_resolve_exe("winget", *_WINGET_FALLBACK_PATHS)
        if winget:
            proc = None
            try:
                proc = subprocess.run(
                    [
                        winget,
                        "install",
                        "-e",
                        "--id",
                        "Ollama.Ollama",
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                        "--silent",
                        "--disable-interactivity",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                winget_err = "winget install timed out (over 15 minutes)."
            if proc is not None:
                combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
                low = combined.lower()
                if proc.returncode == 0:
                    return True, combined or "Ollama installed via winget."
                if any(
                    phrase in low
                    for phrase in (
                        "already installed",
                        "is already installed",
                        "no applicable upgrade",
                        "a newer version was not found",
                        "no newer package",
                        "successfully installed",
                        "no available upgrade",
                        "up to date",
                        "install technology not supported",
                    )
                ):
                    return True, "Ollama is already installed (winget)."
                if proc.returncode in (
                    -1978335189,  # 0x8A15006B - UPDATE_NOT_APPLICABLE
                    -1978335135,  # 0x8A1500A1 - REBOOT_REQUIRED_TO_INSTALL
                    3010,         # ERROR_SUCCESS_REBOOT_REQUIRED
                ):
                    return True, "Ollama installed via winget (reboot may be recommended)."
                self.logger.warning("winget install exit %d: %s", proc.returncode, combined[-2000:])
                winget_err = (combined or f"winget exit {proc.returncode}")[-1500:]

        choco_err: Optional[str] = None
        choco = _windows_resolve_exe("choco", *_CHOCO_FALLBACK_PATHS)
        if choco:
            cproc = None
            try:
                cproc = subprocess.run(
                    [choco, "install", "ollama", "-y"],
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                choco_err = "Chocolatey install timed out (over 15 minutes)."
            if cproc is not None:
                combined = ((cproc.stdout or "") + "\n" + (cproc.stderr or "")).strip()
                low = combined.lower()
                if cproc.returncode == 0:
                    return True, combined or "Ollama installed via Chocolatey."
                if "already installed" in low or "nothing to do" in low:
                    return True, "Ollama is already installed (Chocolatey)."
                choco_err = f"Chocolatey failed (exit {cproc.returncode}). {combined[-800:]}"

        ok_setup, setup_msg = self._windows_install_via_official_setup()
        if ok_setup:
            return True, setup_msg
        ctx: list[str] = []
        if winget_err:
            ctx.append(f"winget: {winget_err[:400]}")
        if choco_err:
            ctx.append(choco_err[:500])
        if ctx:
            return False, f"{setup_msg} Context: {' | '.join(ctx)}"
        return False, setup_msg

    def _install_ollama_darwin(self) -> Tuple[bool, str]:
        brew = shutil.which("brew")
        if not brew:
            return False, "Homebrew not found. Install from https://ollama.com/download/mac"
        for args in (["install", "--cask", "ollama"], ["install", "ollama"]):
            try:
                proc = subprocess.run(
                    [brew] + args,
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return False, "brew install timed out (over 15 minutes)."
            combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            low = combined.lower()
            if proc.returncode == 0:
                return True, combined or "Ollama installed via Homebrew."
            if "already installed" in low or "is already installed" in low:
                return True, "Ollama is already installed (Homebrew)."
        return False, f"brew install failed: {combined[-800:]}" if combined else "brew install failed."

    def _install_ollama_linux(self) -> Tuple[bool, str]:
        return self._upgrade_ollama_linux()

    def install_ollama(self):
        """Install Ollama via platform package manager or official script, then start the service."""
        try:
            try:
                if self._background_stats and self._background_stats.is_alive():
                    self._stop_background.set()
                    self._background_stats.join(timeout=5)
            except Exception:
                pass

            ok, detail = self._run_ollama_install()
            start_result = self.start_service()

            try:
                if hasattr(self, "clear_all_caches") and callable(getattr(self, "clear_all_caches", None)):
                    self.clear_all_caches()
            except Exception:
                pass
            try:
                self._stop_background.clear()
                self._start_background_updates()
            except Exception:
                pass

            if start_result.get("success"):
                api_ok, _ = self._verify_ollama_api(max_retries=5, retry_delay=2)
                if api_ok:
                    if not ok:
                        self.logger.warning(
                            "Install tool reported failure (%s) but Ollama is running; treating as success.",
                            detail,
                        )
                    return {
                        "success": True,
                        "message": f"Ollama installed and running.{'' if ok else ' (package manager reported a warning but the service is healthy)'}",
                    }

            if not ok:
                tag = WINDOWS_UPDATE_FAILURE_TAG if platform.system() == "Windows" else ""
                msg = f"Install step failed: {detail}{tag}"
                if start_result.get("success"):
                    return {"success": False, "message": f"{msg} Ollama was started but API is not responding."}
                return {
                    "success": False,
                    "message": f"{msg} {start_result.get('message', 'Could not start Ollama.')}",
                }

            return {
                "success": False,
                "message": f"Install completed but Ollama failed to start: {start_result.get('message')}. {detail}",
            }
        except Exception as e:
            try:
                self._stop_background.clear()
                self._start_background_updates()
            except Exception:
                pass
            return {"success": False, "message": f"Unexpected error during Ollama install: {str(e)}"}

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
