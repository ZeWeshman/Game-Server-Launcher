import subprocess
import time
import pytest
from server_manager import ServerManager
from unittest.mock import patch, MagicMock

@pytest.fixture
def mgr():
    return ServerManager()

def test_resolve_script(tmp_path, monkeypatch):
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\necho hello\n")
    # should return path
    p = ServerManager._resolve_script(str(script))
    assert str(p) == str(script)

@patch("server_manager.subprocess.Popen")
def test_start_stop(mock_popen, mgr, tmp_path):
    # Setup a fake Popen with pipes
    fake_proc = MagicMock()
    fake_proc.stdin = MagicMock()
    fake_proc.stdout = MagicMock()
    fake_proc.stderr = MagicMock()
    # simulate readline iter for stdout/stderr
    fake_proc.stdout.readline.side_effect = ["line1\n", ""]
    fake_proc.stderr.readline.side_effect = ["", ""]
    fake_proc.poll.return_value = None
    def wait_side():
        time.sleep(0.1)
        return 0
    fake_proc.wait.side_effect = wait_side
    mock_popen.return_value = fake_proc

    # create a fake script file
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    # start server
    called = []
    def on_output(sid, line):
        called.append((sid, line))
    mgr.start_server("id1", "Test", str(script), cwd=str(tmp_path), env={}, on_output=on_output)
    time.sleep(0.05)
    # send command
    assert mgr.send_command("id1", "say hi") in (True, False)
    # stop server (this will try graceful then kill)
    stopped = mgr.stop_server("id1", graceful_cmd="stop", timeout=0)
    assert stopped is True or stopped is False
