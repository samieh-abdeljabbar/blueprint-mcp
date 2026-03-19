"""Config/IaC scanner — Kubernetes, Terraform, SQL, GraphQL, GitHub Actions, .env files."""

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
from src.scanner.base import BaseScanner, ALWAYS_IGNORE

# --- Terraform patterns ---
TF_RESOURCE = re.compile(
    r'^resource\s+"(\w+)"\s+"(\w+)"',
    re.MULTILINE,
)
TF_MODULE = re.compile(
    r'^module\s+"(\w+)"',
    re.MULTILINE,
)
TF_VARIABLE = re.compile(
    r'^variable\s+"(\w+)"',
    re.MULTILINE,
)

# --- SQL patterns ---
SQL_CREATE_TABLE = re.compile(
    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:`|")?(\w+)(?:`|")?',
    re.IGNORECASE,
)
SQL_CREATE_VIEW = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:`|")?(\w+)(?:`|")?',
    re.IGNORECASE,
)
SQL_FOREIGN_KEY = re.compile(
    r'FOREIGN\s+KEY\s*\([^)]+\)\s*REFERENCES\s+(?:`|")?(\w+)(?:`|")?',
    re.IGNORECASE,
)

# --- GraphQL patterns ---
GQL_TYPE = re.compile(
    r'^type\s+(\w+)(?:\s+implements\s+\w+)?\s*\{',
    re.MULTILINE,
)
GQL_INPUT = re.compile(
    r'^input\s+(\w+)\s*\{',
    re.MULTILINE,
)
GQL_QUERY_FIELD = re.compile(
    r'^\s+(\w+)(?:\([^)]*\))?\s*:\s*',
    re.MULTILINE,
)

# Terraform resource type to NodeType mapping
TF_TYPE_MAP = {
    "aws_instance": NodeType.service,
    "aws_lambda_function": NodeType.function,
    "aws_db_instance": NodeType.database,
    "aws_rds_cluster": NodeType.database,
    "aws_dynamodb_table": NodeType.table,
    "aws_s3_bucket": NodeType.database,
    "aws_sqs_queue": NodeType.queue,
    "aws_sns_topic": NodeType.queue,
    "aws_api_gateway_rest_api": NodeType.api,
    "aws_ecs_service": NodeType.container,
    "aws_ecs_task_definition": NodeType.container,
    "google_compute_instance": NodeType.service,
    "google_cloud_run_service": NodeType.container,
    "google_sql_database_instance": NodeType.database,
    "azurerm_app_service": NodeType.service,
    "azurerm_sql_server": NodeType.database,
}

# K8s kind to NodeType mapping
K8S_TYPE_MAP = {
    "Deployment": NodeType.service,
    "StatefulSet": NodeType.service,
    "DaemonSet": NodeType.service,
    "Service": NodeType.api,
    "Ingress": NodeType.route,
    "ConfigMap": NodeType.config,
    "Secret": NodeType.config,
    "CronJob": NodeType.worker,
    "Job": NodeType.worker,
    "Pod": NodeType.container,
    "Namespace": NodeType.module,
}


class ConfigScanner(BaseScanner):
    async def scan(self, path: str) -> ScanResult:
        start = time.time()
        self._table_node_ids: dict[str, str] = {}

        # Check for .env files at project root before walking
        await self._scan_env_files(path)

        # Walk for config files
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [
                d for d in dirnames
                if not self.should_ignore(os.path.join(dirpath, d), path)
            ]
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                if self.should_ignore(full, path):
                    continue

                rel_path = os.path.relpath(full, path)
                ext = os.path.splitext(fname)[1].lower()

                # GitHub Actions workflows
                if self._is_github_workflow(rel_path):
                    await self._scan_github_actions(full, path)
                    self._files_scanned += 1
                # Kubernetes YAML
                elif ext in (".yml", ".yaml") and not self._is_github_workflow(rel_path):
                    await self._scan_yaml_for_k8s(full, path)
                # Terraform
                elif ext == ".tf":
                    await self._scan_terraform(full, path)
                    self._files_scanned += 1
                # SQL
                elif ext == ".sql":
                    await self._scan_sql(full, path)
                    self._files_scanned += 1
                # GraphQL
                elif ext in (".graphql", ".gql"):
                    await self._scan_graphql(full, path)
                    self._files_scanned += 1

        return self._build_result("config_scanner", start)

    def _is_github_workflow(self, rel_path: str) -> bool:
        normalized = rel_path.replace(os.sep, "/")
        return normalized.startswith(".github/workflows/") and (
            normalized.endswith(".yml") or normalized.endswith(".yaml")
        )

    async def _scan_env_files(self, project_root: str):
        """Scan .env files at project root. These are explicitly checked before
        ALWAYS_IGNORE since .env is in the ignore set for venv directories."""
        for entry in os.listdir(project_root):
            if entry == ".env" or (entry.startswith(".env.") and not os.path.isdir(
                os.path.join(project_root, entry)
            )):
                full = os.path.join(project_root, entry)
                if not os.path.isfile(full):
                    continue
                try:
                    with open(full) as f:
                        content = f.read()
                except OSError:
                    continue

                self._files_scanned += 1

                # Extract variable names
                var_names = []
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        var_name = line.split("=", 1)[0].strip()
                        if var_name:
                            var_names.append(var_name)

                await self._track_node(NodeCreateInput(
                    name=entry,
                    type=NodeType.config,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"variables": var_names, "config_type": "env"},
                    source_file=entry,
                ))

    async def _scan_yaml_for_k8s(self, filepath: str, project_root: str):
        """Check if YAML file is a Kubernetes manifest and scan it."""
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                docs = list(yaml.safe_load_all(f))
        except (yaml.YAMLError, OSError):
            return

        for doc in docs:
            if not isinstance(doc, dict):
                continue
            if "apiVersion" not in doc or "kind" not in doc:
                continue

            self._files_scanned += 1

            kind = doc.get("kind", "")
            metadata = doc.get("metadata", {})
            name = metadata.get("name", "") if isinstance(metadata, dict) else ""
            namespace = metadata.get("namespace", "default") if isinstance(metadata, dict) else "default"

            node_type = K8S_TYPE_MAP.get(kind, NodeType.config)

            await self._track_node(NodeCreateInput(
                name=name or kind.lower(),
                type=node_type,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={
                    "kind": kind,
                    "namespace": namespace,
                    "source": "kubernetes",
                },
                source_file=rel_path,
            ))

    async def _scan_github_actions(self, filepath: str, project_root: str):
        """Scan GitHub Actions workflow files."""
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as e:
            self._add_error(rel_path, str(e))
            return

        if not isinstance(data, dict):
            return

        # Workflow name -> script node
        workflow_name = data.get("name", os.path.splitext(os.path.basename(filepath))[0])
        workflow_id, _ = await self._track_node(NodeCreateInput(
            name=workflow_name,
            type=NodeType.script,
            status=NodeStatus.built,
            parent_id=self.root_id,
            metadata={
                "source": "github_actions",
                "triggers": list(data.get("on", {}).keys()) if isinstance(data.get("on"), dict) else [],
            },
            source_file=rel_path,
        ))

        # Jobs -> worker nodes
        jobs = data.get("jobs", {})
        if isinstance(jobs, dict):
            for job_name, job_config in jobs.items():
                if not isinstance(job_config, dict):
                    continue
                runs_on = job_config.get("runs-on", "")
                await self._track_node(NodeCreateInput(
                    name=f"{workflow_name}:{job_name}",
                    type=NodeType.worker,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={
                        "source": "github_actions",
                        "runs_on": runs_on,
                        "workflow": workflow_name,
                    },
                    source_file=rel_path,
                ))

    async def _scan_terraform(self, filepath: str, project_root: str):
        """Scan Terraform .tf files."""
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        # Resources
        for match in TF_RESOURCE.finditer(source):
            resource_type = match.group(1)
            resource_name = match.group(2)
            line = source[:match.start()].count("\n") + 1
            node_type = TF_TYPE_MAP.get(resource_type, NodeType.service)

            await self._track_node(NodeCreateInput(
                name=f"{resource_type}.{resource_name}",
                type=node_type,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={
                    "resource_type": resource_type,
                    "source": "terraform",
                },
                source_file=rel_path,
                source_line=line,
            ))

        # Modules
        for match in TF_MODULE.finditer(source):
            mod_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=mod_name,
                type=NodeType.module,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "terraform"},
                source_file=rel_path,
                source_line=line,
            ))

        # Variables
        for match in TF_VARIABLE.finditer(source):
            var_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=var_name,
                type=NodeType.config,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "terraform", "terraform_type": "variable"},
                source_file=rel_path,
                source_line=line,
            ))

    async def _scan_sql(self, filepath: str, project_root: str):
        """Scan SQL files for CREATE TABLE/VIEW statements and foreign keys."""
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        # CREATE TABLE
        current_table_id = None
        current_table_name = None
        for match in SQL_CREATE_TABLE.finditer(source):
            table_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            node_id, _ = await self._track_node(NodeCreateInput(
                name=table_name,
                type=NodeType.table,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "sql"},
                source_file=rel_path,
                source_line=line,
            ))
            self._table_node_ids[table_name] = node_id

        # CREATE VIEW
        for match in SQL_CREATE_VIEW.finditer(source):
            view_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=view_name,
                type=NodeType.view,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "sql"},
                source_file=rel_path,
                source_line=line,
            ))

        # Foreign keys -> writes_to edges
        # We need to associate FKs with the table they're in
        # Simple approach: split by CREATE TABLE and find FKs within each block
        table_blocks = re.split(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?', source, flags=re.IGNORECASE)
        for block in table_blocks[1:]:  # skip content before first CREATE TABLE
            # Get table name from start of block
            table_match = re.match(r'(?:`|")?(\w+)(?:`|")?', block)
            if not table_match:
                continue
            src_table = table_match.group(1)
            src_id = self._table_node_ids.get(src_table)
            if not src_id:
                continue

            for fk_match in SQL_FOREIGN_KEY.finditer(block):
                ref_table = fk_match.group(1)
                ref_id = self._table_node_ids.get(ref_table)
                if ref_id:
                    await self._track_edge(EdgeCreateInput(
                        source_id=src_id,
                        target_id=ref_id,
                        relationship=EdgeRelationship.writes_to,
                    ))

    async def _scan_graphql(self, filepath: str, project_root: str):
        """Scan GraphQL schema files."""
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        # Types -> schema nodes
        for match in GQL_TYPE.finditer(source):
            type_name = match.group(1)
            line = source[:match.start()].count("\n") + 1

            if type_name in ("Query", "Mutation", "Subscription"):
                # Extract fields as route nodes
                # Find the block content
                block_start = source.index("{", match.start()) + 1
                depth = 1
                pos = block_start
                while pos < len(source) and depth > 0:
                    if source[pos] == "{":
                        depth += 1
                    elif source[pos] == "}":
                        depth -= 1
                    pos += 1
                block = source[block_start:pos - 1]

                for field_match in GQL_QUERY_FIELD.finditer(block):
                    field_name = field_match.group(1)
                    if field_name.startswith("_"):
                        continue
                    prefix = type_name.lower()
                    await self._track_node(NodeCreateInput(
                        name=f"{prefix}:{field_name}",
                        type=NodeType.route,
                        status=NodeStatus.built,
                        parent_id=self.root_id,
                        metadata={
                            "source": "graphql",
                            "operation": type_name.lower(),
                        },
                        source_file=rel_path,
                    ))
            else:
                await self._track_node(NodeCreateInput(
                    name=type_name,
                    type=NodeType.schema,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"source": "graphql"},
                    source_file=rel_path,
                    source_line=line,
                ))

        # Input types -> schema nodes
        for match in GQL_INPUT.finditer(source):
            input_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=input_name,
                type=NodeType.schema,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "graphql", "graphql_type": "input"},
                source_file=rel_path,
                source_line=line,
            ))
