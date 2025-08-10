"""
server_manager.py
Manages server processes, IO capture, and start/stop/restart behavior.
"""

import os
import platform
import shlex
import threading
import time
import subprocess
from pathlib import Path
from typing import Dict, Optional, Callable, List
from logger import get_logger

LOGGER = get_logger(__name__)

class ServerProcess:
    """
    Encapsulate a running server process and its console capture.
    """

    def __init__(self, server_id: str, name: str, popen: subprocess.Popen):
        self.server_id = server_id
        self.name = name
        self.process = popen
        self.stdout_lines: List[str] = []
        self._stop_requested = False
        self._reader_threads: List[threading.Thread] = []
        self._lock = threading.Lock()

    def start_readers(self, on_output: Callable[[str, str], None]) -> None:
        """
        Start background threads to read stdout and stderr and call on_output(server_id, line).
        """
        def _reader(stream, label):
            try:
                for line in iter(stream.readline, ""):
                    if line == "":
                        break
                    text = line.rstrip("\n")
                    with self._lock:
                        self.stdout_lines.append(text)
                    on_output(self.server_id, text)
                stream.close()
            except Exception as e:
                LOGGER.exception("Reader thread error for %s: %s", self.server_id, e)

        # STDOUT
        t_out = threading.Thread(target=_reader, args=(self.process.stdout, "OUT"), daemon=True)
        t_err = threading.Thread(target=_reader, args=(self.process.stderr, "ERR"), daemon=True)
        t_out.start()
        t_err.start()
        self._reader_threads.extend([t_out, t_err])

    def send_command(self, cmd: str) -> bool:
        """
        Send text to process stdin (with newline).
        Returns True if success.
        """
        if self.process.stdin and self.process.poll() is None:
            try:
                self.process.stdin.write((cmd + "\n").encode() if isinstance(self.process.stdin, subprocess.Popen) else (cmd + "\n"))
            except Exception:
                # Fallback to text-mode write
                try:
                    self.process.stdin.write(cmd + "\n")
                except Exception:
                    LOGGER.exception("Failed to send command to %s", self.server_id)
                    return False
            try:
                self.process.stdin.flush()
            except Exception:
                pass
            LOGGER.debug("Sent command to %s: %s", self.server_id, cmd)
            return True
        else:
            LOGGER.warning("Cannot send command; process not running for %s", self.server_id)
            return False

    def collect_console(self) -> str:
        """
        Return collected console output as a single string.
        """
        with self._lock:
            return "\n".join(self.stdout_lines)

class ServerManager:
    """
    Top-level manager for multiple server processes.
    """

    def __init__(self):
        self._processes: Dict[str, ServerProcess] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _resolve_script(path: str) -> Path:
        """
        If the configured script is .sh on Windows, try .bat counterpart and vice versa.

        Raises FileNotFoundError if no suitable script found.
        """
        p = Path(path)
        if p.exists():
            return p
        plat = platform.system().lower()
        # if windows and .sh specified, try .bat
        if plat.startswith("win") and p.suffix == ".sh":
            alt = p.with_suffix(".bat")
            if alt.exists():
                return alt
        # if linux/mac and .bat specified, try .sh
        if not plat.startswith("win") and p.suffix == ".bat":
            alt = p.with_suffix(".sh")
            if alt.exists():
                return alt
        raise FileNotFoundError(f"Script not found: {path}")

    def start_server(self, server_id: str, name: str, start_script: str, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None, on_output: Optional[Callable[[str, str], None]] = None) -> None:
        """
        Start a server subprocess and attach readers.

        Args:
            server_id: unique id for mapping
            name: displayed name (used for logs)
            start_script: path to .sh/.bat
            cwd: working directory
            env: extra env vars
            on_output: callback(server_id, line) for each console line
        """

        with self._lock:
            if server_id in self._processes and self._processes[server_id].process.poll() is None:
                LOGGER.warning("Server %s is already running", server_id)
                return

        try:
            script_path = self._resolve_script(start_script)
        except FileNotFoundError as e:
            LOGGER.exception("Start failed: %s", e)
            raise

        # Build command: on Unix run with bash -c or execute script
        plat = platform.system().lower()
        if plat.startswith("win"):
            cmd = [str(script_path)]
            shell = True  # on windows, allowing .bat execution via shell may be simpler
        else:
            # ensure execution bit maybe; prefer invoking with sh
            cmd = ["/bin/sh", str(script_path)]
            shell = False

        popen = subprocess.Popen(
            cmd,
            cwd=cwd or str(script_path.parent),
            env={**os.environ, **(env or {})},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            shell=shell,
        )
        sp = ServerProcess(server_id, name, popen)
        if on_output:
            sp.start_readers(on_output)
        with self._lock:
            self._processes[server_id] = sp
        # start a watcher to detect unexpected exit
        watcher = threading.Thread(target=self._watch_process, args=(server_id, on_output), daemon=True)
        watcher.start()
        LOGGER.info("Started server %s (%s)", name, server_id)

    def _watch_process(self, server_id: str, on_output: Optional[Callable[[str, str], None]]):
        """
        Wait for process to exit; if it was not requested via stop, call on_unexpected_exit.
        """
        sp = None
        with self._lock:
            sp = self._processes.get(server_id)
        if not sp:
            return
        proc = sp.process
        return_code = proc.wait()
        LOGGER.info("Process %s exited with code %s", server_id, return_code)
        # If stopped via manager.stop_server we set flag _stop_requested; otherwise handle unexpected exit
        if not getattr(sp, "_stop_requested", False):
            # unexpected exit
            LOGGER.warning("Server %s exited unexpectedly", server_id)
            # call on_output to notify UI about exit
            if on_output:
                on_output(server_id, f"[PROCESS EXITED] Return code {return_code}")
            # write latest log file
            logname = f"{sp.name}-latest.log".replace(" ", "_")
            try:
                with open(logname, "w", encoding="utf-8") as fh:
                    fh.write(sp.collect_console())
                LOGGER.info("Wrote latest console to %s", logname)
            except Exception:
                LOGGER.exception("Failed to write latest log for %s", server_id)
            # removal / UI update handled by caller via on_output or eel bindings

    def stop_server(self, server_id: str, graceful_cmd: str = "stop", timeout: int = 15) -> bool:
        """
        Attempt to stop a server by sending graceful_cmd and waiting for timeout seconds.
        If server has force-kill flag in config, it will kill immediately.

        Returns True if process terminated, False otherwise.
        """
        with self._lock:
            sp = self._processes.get(server_id)
        if not sp:
            LOGGER.warning("Stop called for unknown server %s", server_id)
            return True  # already stopped

        # mark stop requested so watcher doesn't treat as unexpected
        sp._stop_requested = True

        # send graceful command
        try:
            sp.send_command(graceful_cmd)
        except Exception:
            LOGGER.exception("Failed to send graceful command to %s", server_id)

        # wait
        start = time.time()
        while sp.process.poll() is None and (time.time() - start) < timeout:
            time.sleep(0.2)

        if sp.process.poll() is None:
            # not stopped: force kill
            try:
                sp.process.kill()
                LOGGER.info("Force killed process for %s", server_id)
            except Exception:
                LOGGER.exception("Failed to kill process for %s", server_id)
            return sp.process.poll() is not None
        LOGGER.info("Server %s stopped cleanly", server_id)
        return True

    def restart_server(self, server_id: str, name: str, start_script: str, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None, on_output: Optional[Callable[[str, str], None]] = None, config_force_kill: bool = False) -> None:
        """
        Restart server: try graceful stop (or force according to config), then start again.
        If graceful stop fails in timeout, caller should be updated to mark config.force_kill_on_stop True.
        """
        stopped = self.stop_server(server_id, graceful_cmd="stop", timeout=15)
        if not stopped:
            # caller should set force_kill_on_stop flag in config if desired
            LOGGER.warning("Graceful stop failed for %s; will force restart", server_id)
            # Try kill attempt
            try:
                with self._lock:
                    sp = self._processes.get(server_id)
                if sp and sp.process.poll() is None:
                    sp.process.kill()
            except Exception:
                LOGGER.exception("Failed to kill during restart for %s", server_id)

        # remove previous process entry
        with self._lock:
            if server_id in self._processes:
                del self._processes[server_id]
        # start fresh
        self.start_server(server_id, name, start_script, cwd=cwd, env=env, on_output=on_output)

    def send_command(self, server_id: str, cmd: str) -> bool:
        """
        Send a command to the server's stdin.
        """
        with self._lock:
            sp = self._processes.get(server_id)
        if not sp:
            LOGGER.warning("Send command to unknown server %s", server_id)
            return False
        return sp.send_command(cmd)

    def is_running(self, server_id: str) -> bool:
        with self._lock:
            sp = self._processes.get(server_id)
        return sp is not None and sp.process.poll() is None

    def get_console(self, server_id: str) -> Optional[str]:
        with self._lock:
            sp = self._processes.get(server_id)
        if not sp:
            return None
        return sp.collect_console()
