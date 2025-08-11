import tempfile
from pathlib import Path
import json
import pytest
from config_manager import ConfigManager

@pytest.fixture
def tmpfile(tmp_path):
    p = tmp_path / "servers.json"
    return p

def test_add_and_get(tmpfile):
    cm = ConfigManager(path=tmpfile)
    s = cm.add({"name": "TestServer", "start_script": "run.sh"})
    assert s.name == "TestServer"
    loaded = cm.get(s.id)
    assert loaded is not None
    assert loaded.start_script == "run.sh"

def test_update_and_remove(tmpfile):
    cm = ConfigManager(path=tmpfile)
    s = cm.add({"name": "X", "start_script": "run.sh"})
    cm.update(s.id, {"name": "Y"})
    s2 = cm.get(s.id)
    assert s2.name == "Y"
    assert cm.remove(s.id) is True
    assert cm.get(s.id) is None
