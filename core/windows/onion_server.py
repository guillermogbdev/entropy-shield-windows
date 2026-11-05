"""Built-in HTTP file server + Tor hidden service on Windows."""
from __future__ import annotations

import functools
import http.server
import os
import socket
import threading
from pathlib import Path
from typing import Callable

from core.config import cfg, cfg_port

from . import paths

_MARKER_BEGIN = "# --- entropy-shield-hs-begin ---"
_MARKER_END = "# --- entropy-shield-hs-end ---"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args) -> None:  # noqa: A003 - stdlib signature
        # The activity log is for the app, not for every HTTP request.
        return


class WindowsOnionServerManager:
    def __init__(self, log: Callable[[str], None]):
        self._log = log
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._hs_dir = paths.data_dir() / "onion-hs"
        self._torrc_path: str | None = None

    def configure(self, torrc_path: str) -> None:
        self._torrc_path = torrc_path
        local_port = cfg_port("onion_server", "local_port")
        hs_port = cfg_port("onion_server", "hs_port")
        paths.ensure_dirs()
        self._hs_dir.mkdir(parents=True, exist_ok=True)
        block = (
            f"\n{_MARKER_BEGIN}\n"
            f'HiddenServiceDir "{str(self._hs_dir).replace(chr(92), "/")}"\n'
            f"HiddenServicePort {hs_port} 127.0.0.1:{local_port}\n"
            f"{_MARKER_END}\n"
        )
        p = Path(torrc_path)
        content = p.read_text(encoding="utf-8") if p.exists() else ""
        content = self._strip_block(content)
        p.write_text(content + block, encoding="utf-8")
        self._log(f"[ONION] Hidden service configured: port {hs_port} → "
                  f"127.0.0.1:{local_port}")

    def remove_config(self, torrc_path: str) -> None:
        p = Path(torrc_path)
        if not p.exists():
            return
        content = p.read_text(encoding="utf-8")
        stripped = self._strip_block(content)
        if stripped != content:
            p.write_text(stripped, encoding="utf-8")

    @staticmethod
    def _strip_block(content: str) -> str:
        while _MARKER_BEGIN in content and _MARKER_END in content:
            start = content.index(_MARKER_BEGIN)
            end = content.index(_MARKER_END) + len(_MARKER_END)
            content = content[:start] + content[end:]
        return content

    def _serve_dir(self) -> Path:
        raw = str(cfg().get("onion_server", "serve_dir")).strip()
        home = Path.home()
        if raw:
            p = Path(os.path.expandvars(os.path.expanduser(raw)))
        else:
            p = home / "Documents" / "Entropy Shield Share"
        p.mkdir(parents=True, exist_ok=True)
        real = p.resolve()
        real_home = home.resolve()
        if os.path.normcase(str(real)) == os.path.normcase(str(real_home)):
            raise RuntimeError(
                "Refusing to publish your whole home folder. Choose a folder "
                "that contains only the files you want to share.")
        if str(real_home).lower().startswith(str(real).lower().rstrip("\\") + "\\"):
            raise RuntimeError(
                "Refusing to publish a folder that contains your home folder.")
        # Do not expose a drive root or a system directory by accident.
        risky = {
            os.path.normcase(str(Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve())),
            os.path.normcase(str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")).resolve())),
            os.path.normcase(str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")).resolve())),
            os.path.normcase(str(Path("C:/Users").resolve())),
        }
        if os.path.normcase(str(real)) in risky or real.parent == real:
            raise RuntimeError(f"Refusing to publish system directory {real}.")
        return real

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    def _rewrite_port(self, port: int) -> None:
        """Point the hidden service at a fallback local port."""
        if not self._torrc_path:
            return
        p = Path(self._torrc_path)
        if not p.exists():
            return
        hs_port = cfg_port("onion_server", "hs_port")
        content = self._strip_block(p.read_text(encoding="utf-8"))
        block = (
            f"\n{_MARKER_BEGIN}\n"
            f'HiddenServiceDir "{str(self._hs_dir).replace(chr(92), "/")}"\n'
            f"HiddenServicePort {hs_port} 127.0.0.1:{port}\n"
            f"{_MARKER_END}\n"
        )
        p.write_text(content + block, encoding="utf-8")

    def start(self) -> None:
        local_port = cfg_port("onion_server", "local_port")
        serve_dir = self._serve_dir()
        handler = functools.partial(_QuietHandler, directory=str(serve_dir))
        try:
            self._server = http.server.ThreadingHTTPServer(
                ("127.0.0.1", local_port), handler)
        except OSError as exc:
            # 10013/10048: the port is reserved (Hyper-V, WSL, another app).
            # Pick a free high port and update the hidden-service block so
            # Tor still forwards correctly.
            fallback = self._free_port()
            if not self._torrc_path:
                raise RuntimeError(
                    f"Cannot bind onion HTTP server on 127.0.0.1:{local_port}: {exc}") from exc
            self._log(f"[ONION] Port {local_port} is unavailable ({exc}); "
                      f"using {fallback} instead.")
            local_port = fallback
            self._rewrite_port(local_port)
            try:
                self._server = http.server.ThreadingHTTPServer(
                    ("127.0.0.1", local_port), handler)
            except OSError as exc2:
                raise RuntimeError(
                    f"Cannot bind onion HTTP server on 127.0.0.1:{local_port}: {exc2}") from exc2
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="onion-http", daemon=True)
        self._thread.start()
        self._log(f"[ONION] HTTP server started on 127.0.0.1:{local_port} "
                  f"— serving: {serve_dir}")

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is None:
            return
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        if self._thread is not None:
            try:
                self._thread.join(timeout=3)
            except Exception:
                pass
        self._thread = None
        self._log("[ONION] HTTP server stopped.")

    def onion_address(self, wait: int = 10) -> str | None:
        hostname = self._hs_dir / "hostname"
        for _ in range(max(1, wait)):
            try:
                value = hostname.read_text(encoding="utf-8").strip()
                if value.endswith(".onion"):
                    return value
            except OSError:
                pass
            threading.Event().wait(1)
        return None
