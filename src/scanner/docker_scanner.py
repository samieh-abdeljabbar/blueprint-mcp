"""Docker scanner — Dockerfile and docker-compose.yml analysis."""

from __future__ import annotations

import os
import re
import time

import yaml

from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    NodeCreateInput,
    NodeStatus,
    NodeType,
    ScanResult,
)
from src.scanner.base import BaseScanner

# Images that map to database type
DB_IMAGES = {"postgres", "postgresql", "mysql", "mariadb", "mongo", "mongodb", "redis", "memcached", "sqlite"}


class DockerScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()

        # Scan Dockerfile
        dockerfile = os.path.join(path, "Dockerfile")
        if os.path.isfile(dockerfile):
            await self._scan_dockerfile(dockerfile, path)
            self._files_scanned += 1

        # Scan docker-compose files
        for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
            compose_path = os.path.join(path, name)
            if os.path.isfile(compose_path):
                await self._scan_compose(compose_path, path)
                self._files_scanned += 1
                break  # Only process first found

        return self._build_result("docker_scanner", start)

    async def _scan_dockerfile(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                content = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        metadata: dict = {}

        # Parse FROM
        from_match = re.search(r"^FROM\s+(\S+)", content, re.MULTILINE)
        if from_match:
            metadata["base_image"] = from_match.group(1)

        # Parse EXPOSE
        expose_matches = re.findall(r"^EXPOSE\s+(\d+)", content, re.MULTILINE)
        if expose_matches:
            metadata["exposed_ports"] = [int(p) for p in expose_matches]

        # Parse CMD
        cmd_match = re.search(r'^CMD\s+(.+)$', content, re.MULTILINE)
        if cmd_match:
            metadata["cmd"] = cmd_match.group(1).strip()

        await self._track_node(NodeCreateInput(
            name=os.path.basename(project_root),
            type=NodeType.container,
            status=NodeStatus.built,
            parent_id=self.root_id,
            metadata=metadata,
            source_file=rel_path,
        ))

    async def _scan_compose(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as e:
            self._add_error(rel_path, str(e))
            return

        if not isinstance(data, dict) or "services" not in data:
            return

        services = data["services"]
        service_node_ids: dict[str, str] = {}

        for svc_name, svc_config in services.items():
            if not isinstance(svc_config, dict):
                continue

            metadata: dict = {"compose_service": svc_name}

            # Determine node type — database images get 'database' type
            image = svc_config.get("image", "")
            node_type = NodeType.service
            if image:
                metadata["image"] = image
                # Check if this is a known DB image
                image_base = image.split(":")[0].split("/")[-1].lower()
                if image_base in DB_IMAGES:
                    node_type = NodeType.database

            # Ports
            ports = svc_config.get("ports", [])
            if ports:
                metadata["ports"] = ports

            # Volumes
            volumes = svc_config.get("volumes", [])
            if volumes:
                metadata["volumes"] = volumes

            # Environment
            env = svc_config.get("environment")
            if isinstance(env, dict):
                metadata["environment"] = list(env.keys())
            elif isinstance(env, list):
                metadata["environment"] = [e.split("=")[0] for e in env if "=" in e]

            node_id, _ = await self._track_node(NodeCreateInput(
                name=svc_name,
                type=node_type,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata=metadata,
                source_file=rel_path,
            ))
            service_node_ids[svc_name] = node_id

        # Create depends_on edges
        for svc_name, svc_config in services.items():
            if not isinstance(svc_config, dict):
                continue
            if svc_name not in service_node_ids:
                continue

            depends = svc_config.get("depends_on", [])
            # Handle both list and dict forms
            if isinstance(depends, dict):
                dep_names = list(depends.keys())
            elif isinstance(depends, list):
                dep_names = depends
            else:
                continue

            for dep_name in dep_names:
                if dep_name in service_node_ids:
                    await self._track_edge(EdgeCreateInput(
                        source_id=service_node_ids[svc_name],
                        target_id=service_node_ids[dep_name],
                        relationship=EdgeRelationship.depends_on,
                    ))
