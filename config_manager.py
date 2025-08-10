"""
config_manager.py
JSON-backed server configuration manager.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import uuid
from dataclasses import dataclass, asdict
from logger import get_logger

LOGGER = get_logger(__name__)

CONFIG_PATH = Path("servers.json")

@dataclass
class ServerConfig:
    id: str
    name: str
    start_script: str
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    force_kill_on_stop: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Return dict suitable for JSON serialization."""
        return asdict(self)

class ConfigManager:
    """
    Manages reading/writing server configurations to a JSON file.
    """

    def __init__(self, path: Path = CONFIG_PATH):
        """
        Initialize the ConfigManager.

        Args:
            path: Path to JSON file with server configs.
        """
        self.path = path
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.path.exists():
            LOGGER.info("Creating new config file at %s", self.path)
            self.save_all([])

    def load_all(self) -> List[ServerConfig]:
        """
        Load all server configurations.

        Returns:
            List of ServerConfig objects.
        """
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            LOGGER.exception("Failed to load config: %s", e)
            return []
        out = []
        for item in data:
            out.append(ServerConfig(**item))
        return out

    def save_all(self, servers: List[ServerConfig]) -> None:
        """
        Save the provided list of server configs to disk.

        Args:
            servers: list of ServerConfig instances
        """
        try:
            with self.path.open("w", encoding="utf-8") as fh:
                json.dump([s.to_dict() for s in servers], fh, indent=2)
            LOGGER.debug("Saved %d server configs", len(servers))
        except Exception:
            LOGGER.exception("Failed to save configs")

    def add(self, partial: Dict[str, Any]) -> ServerConfig:
        """
        Add a new server config.

        Args:
            partial: dict with keys name, start_script, optional cwd/env/force_kill_on_stop

        Returns:
            Created ServerConfig.
        """
        servers = self.load_all()
        sid = str(uuid.uuid4())
        sc = ServerConfig(
            id=sid,
            name=partial["name"],
            start_script=partial["start_script"],
            cwd=partial.get("cwd"),
            env=partial.get("env"),
            force_kill_on_stop=bool(partial.get("force_kill_on_stop", False)),
        )
        servers.append(sc)
        self.save_all(servers)
        LOGGER.info("Added server %s (%s)", sc.name, sc.id)
        return sc

    def update(self, server_id: str, update: Dict[str, Any]) -> Optional[ServerConfig]:
        """
        Update an existing server config.

        Args:
            server_id: id of server to update
            update: dict of fields to update

        Returns:
            Updated ServerConfig or None if not found.
        """
        servers = self.load_all()
        for idx, s in enumerate(servers):
            if s.id == server_id:
                # update fields
                for k, v in update.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
                servers[idx] = s
                self.save_all(servers)
                LOGGER.info("Updated server %s", s.id)
                return s
        LOGGER.warning("Attempted update for unknown server id %s", server_id)
        return None

    def remove(self, server_id: str) -> bool:
        """
        Remove server config by id.

        Returns:
            True if removed, False if not found.
        """
        servers = self.load_all()
        new = [s for s in servers if s.id != server_id]
        if len(new) == len(servers):
            LOGGER.warning("Attempted to remove unknown server id %s", server_id)
            return False
        self.save_all(new)
        LOGGER.info("Removed server %s", server_id)
        return True

    def get(self, server_id: str) -> Optional[ServerConfig]:
        """
        Get server config by id.
        """
        for s in self.load_all():
            if s.id == server_id:
                return s
        return None
