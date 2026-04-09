"""Tests for Windows Ollama install/update when winget and Chocolatey are absent."""

import os
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
import requests
from app.services.ollama_service_control import OLLAMA_WINDOWS_SETUP_EXE_URL, OllamaServiceControl


@pytest.fixture
def control():
    c = OllamaServiceControl()
    c.logger = MagicMock()
    return c


def _mock_response_stream(chunks):
    inner = MagicMock()
    inner.raise_for_status = MagicMock()
    inner.iter_content = MagicMock(side_effect=lambda **kwargs: chunks)
    inner.close = MagicMock()
    return inner


def test_windows_official_setup_success(control, tmp_path):
    path = str(tmp_path / "OllamaSetup.exe")
    open(path, "wb").close()

    with patch("app.services.ollama_service_control.os.close"):
        with patch(
            "app.services.ollama_service_control.tempfile.mkstemp",
            return_value=(-1, path),
        ):
            with patch("app.services.ollama_service_control.requests.get") as mock_get:
                mock_get.return_value = _mock_response_stream([b"x" * (2 * 1024 * 1024)])
                with patch(
                    "app.services.ollama_service_control.subprocess.run"
                ) as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
                    ok, msg = control._windows_install_via_official_setup()
                    assert ok is True
                    assert "official" in msg.lower() or msg == "ok"
                    mock_run.assert_called_once()
                    argv = mock_run.call_args[0][0]
                    assert argv[0] == path
                    assert "/VERYSILENT" in argv
                    assert "/NORESTART" in argv

    assert not os.path.isfile(path), "temp installer should be removed"


def test_windows_official_setup_download_error(control, tmp_path):
    path = str(tmp_path / "OllamaSetup.exe")
    open(path, "wb").close()

    with patch("app.services.ollama_service_control.os.close"):
        with patch(
            "app.services.ollama_service_control.tempfile.mkstemp",
            return_value=(-1, path),
        ):
            with patch(
                "app.services.ollama_service_control._windows_resolve_exe",
                return_value=None,
            ):
                with patch("app.services.ollama_service_control.requests.get") as mock_get:
                    mock_get.side_effect = requests.ConnectionError("no network")
                    with patch(
                        "app.services.ollama_service_control.urllib.request.urlopen",
                        side_effect=urllib.error.URLError("offline"),
                    ):
                        with patch(
                            "app.services.ollama_service_control._windows_powershell_exe",
                            return_value=None,
                        ):
                            ok, msg = control._windows_install_via_official_setup()
                            assert ok is False
                            assert OLLAMA_WINDOWS_SETUP_EXE_URL in msg
                            assert "ollama.com/download/windows" in msg


def test_windows_official_setup_file_too_small(control, tmp_path):
    path = str(tmp_path / "OllamaSetup.exe")
    open(path, "wb").close()

    with patch("app.services.ollama_service_control.os.close"):
        with patch(
            "app.services.ollama_service_control.tempfile.mkstemp",
            return_value=(-1, path),
        ):
            with patch("app.services.ollama_service_control.requests.get") as mock_get:
                mock_get.return_value = _mock_response_stream([b"tiny"])
                ok, msg = control._windows_install_via_official_setup()
                assert ok is False
                assert "too small" in msg.lower()


def test_windows_official_setup_installer_failed(control, tmp_path):
    path = str(tmp_path / "OllamaSetup.exe")
    open(path, "wb").close()

    with patch("app.services.ollama_service_control.os.close"):
        with patch(
            "app.services.ollama_service_control.tempfile.mkstemp",
            return_value=(-1, path),
        ):
            with patch("app.services.ollama_service_control.requests.get") as mock_get:
                mock_get.return_value = _mock_response_stream([b"y" * (2 * 1024 * 1024)])
                with patch(
                    "app.services.ollama_service_control.subprocess.run"
                ) as mock_run:
                    mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="failed")
                    ok, msg = control._windows_install_via_official_setup()
                    assert ok is False
                    assert "exit" in msg.lower() or "2" in msg
                    assert "ollama.com/download/windows" in msg


def test_download_ollama_setup_uses_curl_when_requests_fails(control, tmp_path):
    path = str(tmp_path / "OllamaSetup.exe")
    open(path, "wb").close()

    def which_side_effect(name):
        return r"C:\Windows\System32\curl.exe" if name == "curl" else None

    with patch(
        "app.services.ollama_service_control.requests.get",
        side_effect=requests.ConnectionError("offline"),
    ):
        with patch(
            "app.services.ollama_service_control.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            with patch(
                "app.services.ollama_service_control.shutil.which",
                side_effect=which_side_effect,
            ):
                with patch(
                    "app.services.ollama_service_control.subprocess.run"
                ) as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    ok, err = control._download_ollama_setup_exe(path)
                    assert ok is True
                    assert err == ""
                    mock_run.assert_called_once()
                    args = mock_run.call_args[0][0]
                    assert "curl.exe" in args[0] or args[0].endswith("curl")
                    assert args[-1] == OLLAMA_WINDOWS_SETUP_EXE_URL


def test_download_ollama_setup_uses_urllib_when_requests_fails(control, tmp_path):
    path = str(tmp_path / "OllamaSetup.exe")
    open(path, "wb").close()

    fake_body = BytesIO(b"x" * (2 * 1024 * 1024))

    class _CM:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, n=-1):
            return fake_body.read(n)

    with patch(
        "app.services.ollama_service_control.requests.get",
        side_effect=requests.ConnectionError("offline"),
    ):
        with patch(
            "app.services.ollama_service_control.urllib.request.urlopen",
            return_value=_CM(),
        ):
            ok, err = control._download_ollama_setup_exe(path)
            assert ok is True
            assert err == ""
            assert os.path.getsize(path) >= 2 * 1024 * 1024


@patch("app.services.ollama_service_control._windows_resolve_exe", return_value=None)
@patch.object(OllamaServiceControl, "_windows_install_via_official_setup", return_value=(True, "via setup"))
def test_install_windows_falls_back_to_official_setup(mock_setup, mock_resolve):
    """No winget/choco on PATH or standard paths — only official setup runs."""
    ctl = OllamaServiceControl()
    ctl.logger = MagicMock()
    ok, msg = ctl._install_ollama_windows()
    assert ok is True
    assert msg == "via setup"
    mock_setup.assert_called_once()


@patch.object(
    OllamaServiceControl,
    "_windows_install_via_official_setup",
    return_value=(True, "official ok"),
)
@patch("app.services.ollama_service_control.subprocess.run")
@patch("app.services.ollama_service_control.shutil.which")
def test_upgrade_windows_winget_failure_still_runs_official_installer(
    mock_which, mock_run, _mock_setup
):
    """Broken or failing winget must not skip the OllamaSetup.exe fallback."""

    def which_side_effect(name):
        if name == "winget":
            return r"C:\winget.exe"
        if name == "choco":
            return None
        return None

    mock_which.side_effect = which_side_effect
    mock_run.return_value = MagicMock(returncode=1, stdout="winget bad", stderr="")

    ctl = OllamaServiceControl()
    ctl.logger = MagicMock()
    ok, msg = ctl._upgrade_ollama_windows()
    assert ok is True
    assert msg == "official ok"
    _mock_setup.assert_called_once()
