"""
main.py
Eel app bootstrap and exposed API for UI.
"""

import eel
import webbrowser
import os
from pathlib import Path
import threading
from typing import Dict, Any, List, Optional
from config_manager import ConfigManager, ServerConfig
from server_manager import ServerManager
from logger import get_logger

LOGGER = get_logger(__name__)

WEB_DIR = Path("web")
MAIN_PAGE = "main.html"

cfg = ConfigManager()
mgr = ServerManager()

# Eel initialization
eel.init(str(WEB_DIR))

# Utility to notify front-end console updates. The JS side registers callbacks.
def _on_output(server_id: str, line: str) -> None:
    LOGGER.debug("UI output callback %s: %s", server_id, line)
    try:
        eel.receive_console_line(server_id, line)
    except Exception:
        LOGGER.exception("Failed to call eel.receive_console_line")

@eel.expose
def list_servers() -> List[Dict[str, Any]]:
    """
    Return list of server configs for main window.
    """
    items = cfg.load_all()
    return [s.to_dict() for s in items]

@eel.expose
def add_server(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add server, return new server dict.
    """
    # validate minimal
    if "name" not in data or "start_script" not in data:
        raise ValueError("name and start_script are required")
    server = cfg.add(data)
    return server.to_dict()

@eel.expose
def edit_server(server_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update server config and return updated dict.
    """
    server = cfg.update(server_id, data)
    if not server:
        raise ValueError("server not found")
    return server.to_dict()

@eel.expose
def start_and_open(server_id: str) -> None:
    """
    Open server control window and start the server.
    """
    server = cfg.get(server_id)
    if not server:
        raise ValueError("server not found")

    # open control window in default browser to server_control.html?id=...
    url = f'http://localhost:8000/{WEB_DIR.name}/server_control.html?id={server_id}'
    # eel.start runs a web server for one page; we start eel non-blocking and open windows
    # if eel already running, we just open URL
    webbrowser.open(url)

    # start server in background
    t = threading.Thread(target=_start_server_thread, args=(server,), daemon=True)
    t.start()

def _start_server_thread(server: ServerConfig):
    try:
        mgr.start_server(server.id, server.name, server.start_script, cwd=server.cwd, env=server.env or {}, on_output=_on_output)
    except FileNotFoundError as e:
        eel.show_error(str(e))
    except Exception:
        LOGGER.exception("Failed to start server %s", server.id)
        eel.show_error(f"Failed to start server {server.name}")

@eel.expose
def open_control(server_id: str) -> None:
    """
    Open server control window but don't start the server.
    """
    url = f'http://localhost:8000/{WEB_DIR.name}/server_control.html?id={server_id}'
    webbrowser.open(url)

@eel.expose
def start_server(server_id: str) -> None:
    server = cfg.get(server_id)
    if not server:
        eel.show_error("Server not found")
        return
    threading.Thread(target=_start_server_thread, args=(server,), daemon=True).start()

@eel.expose
def stop_server(server_id: str) -> None:
    """
    Stop server; UI already knows to call this.
    """
    # If server config has force_kill_on_stop True, just kill immediately.
    server = cfg.get(server_id)
    if not server:
        eel.show_error("Server not found")
        return
    # respect force_kill_on_stop flag by passing timeout 0 to cause immediate kill
    if server.force_kill_on_stop:
        success = mgr.stop_server(server_id, graceful_cmd="stop", timeout=0)
    else:
        success = mgr.stop_server(server_id, graceful_cmd="stop", timeout=15)
    eel.notify_server_stopped(server_id, success)

@eel.expose
def restart_server(server_id: str) -> None:
    server = cfg.get(server_id)
    if not server:
        eel.show_error("Server not found")
        return
    # restart in background
    def _restart():
        try:
            mgr.restart_server(server_id, server.name, server.start_script, cwd=server.cwd, env=server.env or {}, on_output=_on_output)
        except Exception as e:
            LOGGER.exception("Restart failed")
            eel.show_error(f"Restart failed: {e}")
    threading.Thread(target=_restart, daemon=True).start()

@eel.expose
def send_command(server_id: str, command: str) -> None:
    ok = mgr.send_command(server_id, command)
    if not ok:
        eel.show_error("Failed to send command (server not running?)")

def _start_eel():
    # pick a free port; eel.start supports port = 8000 default if not configured; we'll use 8000
    # using block=False to continue Python thread and allow opening multiple browser windows
    eel.start(str(WEB_DIR / MAIN_PAGE), mode=None, port=8000, size=(900, 600), block=False)  # mode=None uses default browser

if __name__ == "__main__":
    # Start eel server and open main page
    _start_eel()
    # Keep the main thread alive
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        LOGGER.info("Shutting down")
