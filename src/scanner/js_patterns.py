"""Compiled regex patterns for JavaScript/TypeScript scanner."""

from __future__ import annotations

import re

# --- Import patterns ---

# ES6: import X from './path'  |  import { X } from './path'  |  import './path'
# Handles multiline imports via DOTALL on the from-path portion
ES6_IMPORT = re.compile(
    r"""import\s+(?:.*?\s+from\s+)?['"]([^'"]+)['"]""",
    re.DOTALL,
)

# CommonJS: const X = require('./path')  |  require('./path')
CJS_REQUIRE = re.compile(
    r"""require\(\s*['"]([^'"]+)['"]\s*\)"""
)

# Dynamic: import('./path')
DYNAMIC_IMPORT = re.compile(
    r"""import\(\s*['"]([^'"]+)['"]\s*\)"""
)

# --- Route patterns ---

# Express/Fastify: app.get('/path', ...), router.post('/path', ...)
ROUTE_PATTERN = re.compile(
    r"""(?:app|router|server)\.(get|post|put|delete|patch)\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)

# Next.js API route exports: export async function GET/POST/PUT/DELETE/PATCH
NEXTJS_API_EXPORT = re.compile(
    r"""export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH)\b"""
)

# --- Component patterns ---

# export default function PascalName
REACT_EXPORT_DEFAULT = re.compile(
    r"""export\s+default\s+function\s+([A-Z]\w+)"""
)

# export function PascalName
REACT_EXPORT_NAMED = re.compile(
    r"""export\s+function\s+([A-Z]\w+)"""
)

# export const PascalName = (...) =>
REACT_ARROW_COMPONENT = re.compile(
    r"""export\s+(?:const|let)\s+([A-Z]\w+)\s*=\s*(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>"""
)

# --- Re-export patterns ---

# export { X } from './path'  |  export type { X } from './path'
REEXPORT_NAMED = re.compile(
    r"""export\s+(?:type\s+)?\{[^}]*\}\s+from\s+['"]([^'"]+)['"]"""
)

# export * from './path'  |  export * as X from './path'
REEXPORT_ALL = re.compile(
    r"""export\s+\*\s+(?:as\s+\w+\s+)?from\s+['"]([^'"]+)['"]"""
)

# --- React-specific patterns ---

# export function useAuth(...)  |  export default function useAuth(...)
CUSTOM_HOOK = re.compile(
    r"""export\s+(?:default\s+)?function\s+(use[A-Z]\w*)"""
)

# export const useAuth = ...
CUSTOM_HOOK_ARROW = re.compile(
    r"""export\s+(?:const|let)\s+(use[A-Z]\w*)\s*="""
)

# const ThemeContext = createContext(...)  |  React.createContext(...)
CREATE_CONTEXT = re.compile(
    r"""(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:React\.)?createContext"""
)

# const Button = forwardRef(...)  |  React.forwardRef(...)
FORWARD_REF = re.compile(
    r"""(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:React\.)?forwardRef"""
)

# const MemoizedList = memo(...)  |  React.memo(...)
REACT_MEMO = re.compile(
    r"""(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:React\.)?memo\("""
)

# 'use client'  |  "use server"
USE_DIRECTIVE = re.compile(
    r"""^['"]use\s+(client|server)['"]""",
    re.MULTILINE,
)

# --- API call patterns ---

# fetch('/api/users')
FETCH_API_CALL = re.compile(
    r"""fetch\(\s*['"](/api/[^'"]+)['"]"""
)

# axios.get('/api/users')
AXIOS_API_CALL = re.compile(
    r"""axios\.(?:get|post|put|delete|patch)\(\s*['"](/api/[^'"]+)['"]"""
)

# --- Class patterns ---

# class X extends Y {
CLASS_EXTENDS = re.compile(
    r"""class\s+(\w+)\s+extends\s+(\w+)"""
)

# class X {  (standalone, no extends)
CLASS_STANDALONE = re.compile(
    r"""(?:export\s+)?class\s+(\w+)\s*\{"""
)

# --- Middleware patterns ---

# app.use(...)  — extract function name if present
MIDDLEWARE_USE = re.compile(
    r"""(?:app|router|server)\.use\(\s*(\w+)"""
)

# --- ORM patterns ---

# Prisma: model X {
PRISMA_MODEL = re.compile(
    r"""^model\s+(\w+)\s*\{""",
    re.MULTILINE,
)

# Drizzle: export const X = pgTable('name', ...)  |  mysqlTable  |  sqliteTable
DRIZZLE_TABLE = re.compile(
    r"""(?:pgTable|mysqlTable|sqliteTable)\(\s*['"](\w+)['"]"""
)

# TypeORM: @Entity('name') or @Entity()
TYPEORM_ENTITY = re.compile(
    r"""@Entity\(\s*(?:['"](\w+)['"])?\s*\)"""
)

# --- File extensions ---

JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

# Extensions to try when resolving imports
RESOLVE_EXTENSIONS = [
    ".ts", ".tsx", ".js", ".jsx",
    "/index.ts", "/index.tsx", "/index.js", "/index.jsx",
]

# Config file names
CONFIG_FILES = {
    "next.config.js", "next.config.mjs", "next.config.ts",
    "vite.config.js", "vite.config.ts",
    "webpack.config.js",
    "tsconfig.json",
    "tailwind.config.js", "tailwind.config.ts",
    "postcss.config.js", "postcss.config.mjs",
    "eslint.config.js", "eslint.config.mjs",
    ".eslintrc.js", ".eslintrc.json",
    "jest.config.js", "jest.config.ts",
    "vitest.config.ts",
}
