"""SQL/Database schema scanner — deep detection across SQL, Prisma, ORMs, and migrations."""

from __future__ import annotations

import os
import re
import time

from src.models import (
    EdgeCreateInput,
    EdgeRelationship,
    NodeCreateInput,
    NodeStatus,
    NodeType,
    ScanResult,
)
from src.scanner.base import BaseScanner

# Optional sqlparse for robust column extraction
try:
    import sqlparse
    HAS_SQLPARSE = True
except ImportError:
    HAS_SQLPARSE = False

# Column limit — beyond this, store in metadata instead of child nodes
COLUMN_NODE_LIMIT = 15

# =============================================================================
# SQL file patterns
# =============================================================================

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
SQL_CREATE_INDEX = re.compile(
    r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:`|")?(\w+)(?:`|")?\s+ON\s+(?:`|")?(\w+)(?:`|")?',
    re.IGNORECASE,
)
SQL_CREATE_TRIGGER = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+(?:`|")?(\w+)(?:`|")?\s+.*?\bON\s+(?:`|")?(\w+)(?:`|")?',
    re.IGNORECASE | re.DOTALL,
)
SQL_CREATE_FUNCTION = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:`|")?(\w+)(?:`|")?',
    re.IGNORECASE,
)
SQL_ALTER_TABLE_FK = re.compile(
    r'ALTER\s+TABLE\s+(?:`|")?(\w+)(?:`|")?\s+ADD\s+(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY\s*\([^)]+\)\s*REFERENCES\s+(?:`|")?(\w+)(?:`|")?',
    re.IGNORECASE,
)
VIEW_FROM_TABLES = re.compile(
    r'\b(?:FROM|JOIN)\s+(?:`|")?(\w+)(?:`|")?',
    re.IGNORECASE,
)

# Column-line constraint keywords to skip
CONSTRAINT_PREFIXES = frozenset({
    'constraint', 'primary', 'foreign', 'unique', 'check', 'index',
})

# =============================================================================
# Prisma patterns
# =============================================================================

PRISMA_DATASOURCE = re.compile(
    r'datasource\s+\w+\s*\{[^}]*provider\s*=\s*"(\w+)"',
    re.DOTALL,
)
PRISMA_MODEL = re.compile(
    r'^model\s+(\w+)\s*\{',
    re.MULTILINE,
)
PRISMA_FIELD = re.compile(
    r'^\s+(\w+)\s+(\w+)(\[\])?\s*(.*)',
    re.MULTILINE,
)
PRISMA_RELATION = re.compile(
    r'@relation\(fields:\s*\[(\w+)\]',
)

# =============================================================================
# Django migration patterns
# =============================================================================

DJANGO_CREATE_MODEL = re.compile(
    r"migrations\.CreateModel\(\s*name='(\w+)'",
)
DJANGO_FK_FIELD = re.compile(
    r"models\.ForeignKey\([^)]*to='(?:\w+\.)?(\w+)'",
)

# =============================================================================
# Alembic migration patterns
# =============================================================================

ALEMBIC_CREATE_TABLE = re.compile(
    r"op\.create_table\(\s*'(\w+)'",
)
ALEMBIC_FK_CONSTRAINT = re.compile(
    r"sa\.ForeignKeyConstraint\(\s*\[[^\]]+\]\s*,\s*\['(\w+)\.\w+'\]",
)

# =============================================================================
# TypeORM patterns
# =============================================================================

TYPEORM_ENTITY = re.compile(
    r'@Entity\(\s*["\'](\w+)["\']\s*\)',
)
TYPEORM_COLUMN = re.compile(
    r'@(?:PrimaryGeneratedColumn|Column)\(.*?\)\s*\n\s*(\w+)\s*:',
    re.DOTALL,
)
TYPEORM_RELATION = re.compile(
    r'@(?:ManyToOne|OneToOne|OneToMany|ManyToMany)\(\s*\(\)\s*=>\s*(\w+)',
)

# =============================================================================
# Knex / Sequelize migration patterns
# =============================================================================

KNEX_CREATE_TABLE = re.compile(
    r'\.createTable\(\s*["\'](\w+)["\']',
)
KNEX_REFERENCES_INTABLE = re.compile(
    r'\.references\(\s*["\'](\w+)["\']\s*\)\s*\.inTable\(\s*["\'](\w+)["\']',
)

# =============================================================================
# Connection string patterns
# =============================================================================

CONN_STRING_PATTERN = re.compile(
    r'^(\w+)=(\w+)://(.+)$',
    re.MULTILINE,
)


class SQLScanner(BaseScanner):
    """Scans SQL files, Prisma schemas, ORM migrations, and connection strings."""

    async def scan(self, path: str) -> ScanResult:
        start = time.time()

        # Internal state for FK edge resolution
        self._table_node_ids: dict[str, str] = {}
        self._deferred_fk_edges: list[tuple[str, str]] = []

        # Walk the project tree
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
                rel_dir = os.path.relpath(dirpath, path)

                try:
                    # SQL files
                    if ext == ".sql":
                        await self._scan_sql_file(full, path)

                    # Prisma schema
                    elif ext == ".prisma":
                        await self._scan_prisma_schema(full, path)

                    # Django migrations
                    elif (ext == ".py"
                          and self._is_django_migration(rel_path)
                          and fname != "__init__.py"):
                        await self._scan_django_migration(full, path)

                    # Alembic migrations
                    elif (ext == ".py"
                          and self._is_alembic_migration(rel_path)
                          and fname != "__init__.py"):
                        await self._scan_alembic_migration(full, path)

                    # TypeORM entities
                    elif ext == ".ts" and fname.endswith(".entity.ts"):
                        await self._scan_typeorm_entity(full, path)

                    # Knex/Sequelize JS/TS migrations
                    elif ext in (".ts", ".js") and self._is_js_migration(rel_path):
                        await self._scan_js_migration(full, path)

                except Exception as e:
                    self._add_error(
                        os.path.relpath(full, path),
                        f"SQL scanner error: {e}",
                    )

        # Scan .env files at project root for connection strings
        await self._scan_connection_strings(path)

        # Resolve deferred FK edges
        await self._resolve_deferred_fks()

        return self._build_result("sql_scanner", start)

    # =========================================================================
    # Dispatch helpers
    # =========================================================================

    def _is_django_migration(self, rel_path: str) -> bool:
        parts = rel_path.replace(os.sep, "/").split("/")
        return "migrations" in parts

    def _is_alembic_migration(self, rel_path: str) -> bool:
        normalized = rel_path.replace(os.sep, "/")
        return normalized.startswith("alembic/versions/") or "/alembic/versions/" in normalized

    def _is_js_migration(self, rel_path: str) -> bool:
        normalized = rel_path.replace(os.sep, "/")
        parts = normalized.split("/")
        for part in parts:
            if "migration" in part.lower():
                return True
        return False

    # =========================================================================
    # SQL file scanner
    # =========================================================================

    async def _scan_sql_file(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        self._files_scanned += 1

        # --- CREATE TABLE with columns ---
        for match in SQL_CREATE_TABLE.finditer(source):
            table_name = match.group(1)
            line = source[:match.start()].count("\n") + 1

            # Parse columns
            columns = self._extract_columns(source, match.start())

            # Determine metadata based on column count
            metadata: dict = {"source": "sql"}
            if len(columns) > COLUMN_NODE_LIMIT:
                metadata["columns"] = [c["name"] for c in columns]
                metadata["total_columns"] = len(columns)

            node_id, _ = await self._track_node(NodeCreateInput(
                name=table_name,
                type=NodeType.table,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata=metadata,
                source_file=rel_path,
                source_line=line,
            ))
            self._table_node_ids[table_name] = node_id

            # Create column child nodes if within limit
            if len(columns) <= COLUMN_NODE_LIMIT:
                for col in columns:
                    col_meta = {"data_type": col.get("data_type", "unknown")}
                    if col.get("primary_key"):
                        col_meta["primary_key"] = True
                    if col.get("nullable") is not None:
                        col_meta["nullable"] = col["nullable"]
                    await self._track_node(NodeCreateInput(
                        name=col["name"],
                        type=NodeType.column,
                        status=NodeStatus.built,
                        parent_id=node_id,
                        metadata=col_meta,
                        source_file=rel_path,
                    ))

        # --- FK edges from CREATE TABLE ---
        table_blocks = re.split(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?',
            source, flags=re.IGNORECASE,
        )
        for block in table_blocks[1:]:
            table_match = re.match(r'(?:`|")?(\w+)(?:`|")?', block)
            if not table_match:
                continue
            src_table = table_match.group(1)
            for fk_match in SQL_FOREIGN_KEY.finditer(block):
                ref_table = fk_match.group(1)
                self._deferred_fk_edges.append((src_table, ref_table))

        # --- CREATE VIEW with source table edges ---
        for match in SQL_CREATE_VIEW.finditer(source):
            view_name = match.group(1)
            line = source[:match.start()].count("\n") + 1

            view_id, _ = await self._track_node(NodeCreateInput(
                name=view_name,
                type=NodeType.view,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "sql"},
                source_file=rel_path,
                source_line=line,
            ))

            # Extract source tables from the view body (text after AS)
            view_body_start = source.find("AS", match.end())
            if view_body_start != -1:
                # Find end of view (next semicolon or next CREATE/ALTER or EOF)
                rest = source[view_body_start:]
                end_match = re.search(r';|\bCREATE\b|\bALTER\b', rest, re.IGNORECASE)
                view_body = rest[:end_match.start()] if end_match else rest

                for from_match in VIEW_FROM_TABLES.finditer(view_body):
                    ref_table = from_match.group(1)
                    # Skip SQL keywords that might match
                    if ref_table.upper() in ("SELECT", "WHERE", "AS", "ON", "AND", "OR", "SET", "INTO", "VALUES"):
                        continue
                    ref_id = self._table_node_ids.get(ref_table)
                    if ref_id:
                        await self._track_edge(EdgeCreateInput(
                            source_id=view_id,
                            target_id=ref_id,
                            relationship=EdgeRelationship.reads_from,
                        ))

        # --- CREATE INDEX -> annotation ---
        for match in SQL_CREATE_INDEX.finditer(source):
            index_name = match.group(1)
            table_name = match.group(2)
            table_id = self._table_node_ids.get(table_name)
            if table_id:
                # Store index as annotation via metadata update
                await self._track_node(NodeCreateInput(
                    name=table_name,
                    type=NodeType.table,
                    status=NodeStatus.built,
                    parent_id=self.root_id,
                    metadata={"source": "sql", "indexes": [index_name]},
                    source_file=rel_path,
                ))

        # --- CREATE FUNCTION ---
        for match in SQL_CREATE_FUNCTION.finditer(source):
            func_name = match.group(1)
            line = source[:match.start()].count("\n") + 1
            await self._track_node(NodeCreateInput(
                name=func_name,
                type=NodeType.function,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "sql"},
                source_file=rel_path,
                source_line=line,
            ))

        # --- CREATE TRIGGER ---
        for match in SQL_CREATE_TRIGGER.finditer(source):
            trigger_name = match.group(1)
            table_name = match.group(2)
            line = source[:match.start()].count("\n") + 1

            trigger_id, _ = await self._track_node(NodeCreateInput(
                name=trigger_name,
                type=NodeType.function,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "sql", "trigger": True},
                source_file=rel_path,
                source_line=line,
            ))

            # observes edge to the table
            table_id = self._table_node_ids.get(table_name)
            if table_id:
                await self._track_edge(EdgeCreateInput(
                    source_id=trigger_id,
                    target_id=table_id,
                    relationship=EdgeRelationship.observes,
                ))

        # --- ALTER TABLE FK ---
        for match in SQL_ALTER_TABLE_FK.finditer(source):
            src_table = match.group(1)
            ref_table = match.group(2)
            self._deferred_fk_edges.append((src_table, ref_table))

    # =========================================================================
    # Column extraction
    # =========================================================================

    def _extract_columns(self, source: str, table_start: int) -> list[dict]:
        """Extract column definitions from a CREATE TABLE statement."""
        # Find the opening paren
        paren_pos = source.find("(", table_start)
        if paren_pos == -1:
            return []

        # Find matching closing paren using balanced-paren counter
        depth = 1
        pos = paren_pos + 1
        while pos < len(source) and depth > 0:
            if source[pos] == "(":
                depth += 1
            elif source[pos] == ")":
                depth -= 1
            pos += 1

        body = source[paren_pos + 1 : pos - 1]

        # Split by commas at depth=0
        elements = self._split_at_depth_zero(body)

        columns = []
        for elem in elements:
            elem = elem.strip()
            if not elem:
                continue

            # Skip constraint lines
            first_word = elem.split()[0].lower() if elem.split() else ""
            if first_word in CONSTRAINT_PREFIXES:
                continue

            col = self._parse_column_def(elem)
            if col:
                columns.append(col)

        return columns

    def _split_at_depth_zero(self, text: str) -> list[str]:
        """Split text by commas, but only at paren depth 0."""
        parts = []
        current = []
        depth = 0
        for ch in text:
            if ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current))
        return parts

    def _parse_column_def(self, elem: str) -> dict | None:
        """Parse a single column definition line."""
        # Remove leading/trailing whitespace and newlines
        elem = " ".join(elem.split())
        parts = elem.split()
        if len(parts) < 2:
            return None

        col_name = parts[0].strip('`"')
        # Skip if name looks like a keyword
        if col_name.upper() in ("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "INDEX", "KEY"):
            return None

        data_type = parts[1].strip('`"')
        # Handle types with parens like VARCHAR(255)
        if len(parts) > 2 and parts[1].endswith("(") or "(" in data_type:
            # Rebuild type with size spec
            type_str = " ".join(parts[1:])
            paren_end = type_str.find(")")
            if paren_end != -1:
                data_type = type_str[:paren_end + 1]

        upper_elem = elem.upper()
        primary_key = "PRIMARY KEY" in upper_elem
        nullable = "NOT NULL" not in upper_elem

        return {
            "name": col_name,
            "data_type": data_type,
            "primary_key": primary_key,
            "nullable": nullable,
        }

    # =========================================================================
    # Prisma schema scanner
    # =========================================================================

    async def _scan_prisma_schema(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        self._files_scanned += 1

        # Datasource -> database node
        ds_match = PRISMA_DATASOURCE.search(source)
        if ds_match:
            provider = ds_match.group(1)
            await self._track_node(NodeCreateInput(
                name=f"{provider}_database",
                type=NodeType.database,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "prisma", "provider": provider},
                source_file=rel_path,
            ))

        # Models -> table nodes with columns
        model_positions = list(PRISMA_MODEL.finditer(source))
        for i, match in enumerate(model_positions):
            model_name = match.group(1)
            line = source[:match.start()].count("\n") + 1

            # Find model body (between { and })
            body_start = source.index("{", match.start()) + 1
            if i + 1 < len(model_positions):
                body_end = source.rfind("}", body_start, model_positions[i + 1].start())
            else:
                body_end = source.find("}", body_start)
            if body_end == -1:
                body_end = len(source)
            body = source[body_start:body_end]

            node_id, _ = await self._track_node(NodeCreateInput(
                name=model_name,
                type=NodeType.table,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "prisma"},
                source_file=rel_path,
                source_line=line,
            ))
            self._table_node_ids[model_name] = node_id

            # Parse fields
            for field_match in PRISMA_FIELD.finditer(body):
                field_name = field_match.group(1)
                field_type = field_match.group(2)
                is_array = field_match.group(3) is not None
                rest = field_match.group(4)

                # Skip relation arrays (reverse side, e.g. posts Post[])
                if is_array:
                    continue

                # Check if it's a @relation field
                rel_match = PRISMA_RELATION.search(rest)
                if rel_match:
                    # This field references another model
                    self._deferred_fk_edges.append((model_name, field_type))
                    continue

                # Skip non-scalar types (model references without @relation are handled above)
                scalar_types = {"Int", "String", "Boolean", "Float", "DateTime", "Decimal", "BigInt", "Bytes", "Json"}
                base_type = field_type.rstrip("?")
                if base_type not in scalar_types:
                    continue

                # Create column child node
                await self._track_node(NodeCreateInput(
                    name=field_name,
                    type=NodeType.column,
                    status=NodeStatus.built,
                    parent_id=node_id,
                    metadata={
                        "data_type": field_type,
                        "source": "prisma",
                    },
                    source_file=rel_path,
                ))

    # =========================================================================
    # Django migration scanner
    # =========================================================================

    async def _scan_django_migration(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        # Only scan files that look like Django migrations
        if "migrations.CreateModel" not in source:
            return

        self._files_scanned += 1

        # Find CreateModel blocks
        for match in DJANGO_CREATE_MODEL.finditer(source):
            model_name = match.group(1)
            # Django convention: lowercase model name as table
            table_name = model_name.lower()

            node_id, _ = await self._track_node(NodeCreateInput(
                name=table_name,
                type=NodeType.table,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "django_migration", "model_name": model_name},
                source_file=rel_path,
            ))
            self._table_node_ids[table_name] = node_id
            # Also map by model name for FK resolution
            self._table_node_ids[model_name] = node_id

        # Find FK fields — these reference other models
        # We need to associate FK with the model it belongs to
        # Simple approach: find CreateModel blocks and their FK fields
        blocks = source.split("migrations.CreateModel(")
        for block in blocks[1:]:
            name_match = re.search(r"name='(\w+)'", block)
            if not name_match:
                continue
            src_model = name_match.group(1)

            for fk_match in DJANGO_FK_FIELD.finditer(block):
                ref_model = fk_match.group(1)
                self._deferred_fk_edges.append((src_model.lower(), ref_model.lower()))
                # Also try original case
                self._deferred_fk_edges.append((src_model, ref_model))

    # =========================================================================
    # Alembic migration scanner
    # =========================================================================

    async def _scan_alembic_migration(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        # Only scan files that look like Alembic migrations
        if "op.create_table" not in source:
            return

        self._files_scanned += 1

        # Find create_table calls
        for match in ALEMBIC_CREATE_TABLE.finditer(source):
            table_name = match.group(1)

            node_id, _ = await self._track_node(NodeCreateInput(
                name=table_name,
                type=NodeType.table,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "alembic_migration"},
                source_file=rel_path,
            ))
            self._table_node_ids[table_name] = node_id

        # Find FK constraints — associate with the create_table block they're in
        table_blocks = source.split("op.create_table(")
        for block in table_blocks[1:]:
            name_match = re.match(r"\s*'(\w+)'", block)
            if not name_match:
                continue
            src_table = name_match.group(1)

            for fk_match in ALEMBIC_FK_CONSTRAINT.finditer(block):
                ref_table = fk_match.group(1)
                self._deferred_fk_edges.append((src_table, ref_table))

    # =========================================================================
    # TypeORM entity scanner
    # =========================================================================

    async def _scan_typeorm_entity(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)
        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        self._files_scanned += 1

        # Find @Entity decorator
        entity_match = TYPEORM_ENTITY.search(source)
        if not entity_match:
            return

        table_name = entity_match.group(1)
        node_id, _ = await self._track_node(NodeCreateInput(
            name=table_name,
            type=NodeType.table,
            status=NodeStatus.built,
            parent_id=self.root_id,
            metadata={"source": "typeorm"},
            source_file=rel_path,
        ))
        self._table_node_ids[table_name] = node_id

        # Find @Column and @PrimaryGeneratedColumn
        for col_match in TYPEORM_COLUMN.finditer(source):
            col_name = col_match.group(1)
            await self._track_node(NodeCreateInput(
                name=col_name,
                type=NodeType.column,
                status=NodeStatus.built,
                parent_id=node_id,
                metadata={"source": "typeorm"},
                source_file=rel_path,
            ))

        # Find relation decorators
        for rel_match in TYPEORM_RELATION.finditer(source):
            ref_entity = rel_match.group(1)
            # We can't resolve the target table name here since it may not be scanned yet
            # Store as deferred with the entity class name
            self._deferred_fk_edges.append((table_name, ref_entity))

    # =========================================================================
    # JS migration scanner (Knex/Sequelize)
    # =========================================================================

    async def _scan_js_migration(self, filepath: str, project_root: str):
        rel_path = os.path.relpath(filepath, project_root)

        # Skip TypeORM entities (handled separately)
        if filepath.endswith(".entity.ts"):
            return

        try:
            with open(filepath) as f:
                source = f.read()
        except OSError as e:
            self._add_error(rel_path, str(e))
            return

        # Only scan files with createTable
        if "createTable" not in source:
            return

        self._files_scanned += 1

        # Find createTable calls
        for match in KNEX_CREATE_TABLE.finditer(source):
            table_name = match.group(1)
            node_id, _ = await self._track_node(NodeCreateInput(
                name=table_name,
                type=NodeType.table,
                status=NodeStatus.built,
                parent_id=self.root_id,
                metadata={"source": "knex_migration"},
                source_file=rel_path,
            ))
            self._table_node_ids[table_name] = node_id

        # Find .references().inTable() patterns
        for ref_match in KNEX_REFERENCES_INTABLE.finditer(source):
            ref_table = ref_match.group(2)
            # Find which createTable block this belongs to
            # Look backwards from match to find the closest createTable
            preceding = source[:ref_match.start()]
            table_matches = list(KNEX_CREATE_TABLE.finditer(preceding))
            if table_matches:
                src_table = table_matches[-1].group(1)
                self._deferred_fk_edges.append((src_table, ref_table))

    # =========================================================================
    # Connection string scanner
    # =========================================================================

    async def _scan_connection_strings(self, project_root: str):
        """Scan .env files at project root for DATABASE_URL, REDIS_URL, etc."""
        for entry in os.listdir(project_root):
            if not (entry == ".env" or entry.startswith(".env.")):
                continue
            full = os.path.join(project_root, entry)
            if not os.path.isfile(full):
                continue

            try:
                with open(full) as f:
                    content = f.read()
            except OSError:
                continue

            self._files_scanned += 1

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                var_name, _, value = line.partition("=")
                var_name = var_name.strip()
                value = value.strip().strip("'\"")

                # Check for known connection string patterns
                if var_name.upper().endswith("_URL") or var_name.upper().endswith("_URI"):
                    protocol_match = re.match(r'(\w+)://', value)
                    if not protocol_match:
                        continue

                    protocol = protocol_match.group(1).lower()

                    # Determine node type from protocol
                    if protocol in ("redis", "rediss"):
                        node_type = NodeType.cache
                        provider = "redis"
                    elif protocol in ("mongodb", "mongodb+srv"):
                        node_type = NodeType.database
                        provider = "mongodb"
                    elif protocol in ("postgresql", "postgres", "mysql", "sqlite", "mssql"):
                        node_type = NodeType.database
                        provider = protocol
                    else:
                        node_type = NodeType.database
                        provider = protocol

                    # NEVER store credentials — only provider and var name
                    await self._track_node(NodeCreateInput(
                        name=f"{var_name.lower()}_store",
                        type=node_type,
                        status=NodeStatus.built,
                        parent_id=self.root_id,
                        metadata={
                            "source": "connection_string",
                            "provider": provider,
                            "env_var": var_name,
                        },
                    ))

    # =========================================================================
    # Deferred FK resolution
    # =========================================================================

    async def _resolve_deferred_fks(self):
        """Resolve all deferred FK edges now that all tables are registered."""
        seen: set[tuple[str, str]] = set()
        for src_name, tgt_name in self._deferred_fk_edges:
            src_id = self._table_node_ids.get(src_name)
            tgt_id = self._table_node_ids.get(tgt_name)
            if src_id and tgt_id and src_id != tgt_id:
                key = (src_id, tgt_id)
                if key not in seen:
                    seen.add(key)
                    await self._track_edge(EdgeCreateInput(
                        source_id=src_id,
                        target_id=tgt_id,
                        relationship=EdgeRelationship.reads_from,
                    ))
