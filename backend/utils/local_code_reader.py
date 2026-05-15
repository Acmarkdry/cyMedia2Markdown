# -*- coding: UTF-8 -*-

import os
from pathlib import Path
from typing import List, Optional

from config.log import get_logger

logger = get_logger(__name__)

# Directories to exclude from code search
EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "Intermediate",
    "Binaries",
    "DerivedDataCache",
    "Build",
    "__pycache__",
    ".venv",
    "dist",
    ".next",
    "vendor",
    "ThirdParty",
    ".idea",
    ".vscode",
    ".vs",
    "obj",
    "bin",
    "packages",
    ".tox",
    ".eggs",
    "*.egg-info",
}

# Default file patterns for source code detection
DEFAULT_FILE_PATTERNS = [
    "*.h",
    "*.cpp",
    "*.py",
    "*.ts",
    "*.js",
    "*.tsx",
    "*.jsx",
    "*.cs",
    "*.java",
    "*.go",
    "*.rs",
]

# Language mapping from file extension
EXTENSION_LANGUAGE_MAP = {
    ".h": "c/c++",
    ".hpp": "c++",
    ".cpp": "c++",
    ".cc": "c++",
    ".cxx": "c++",
    ".c": "c",
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript-react",
    ".js": "javascript",
    ".jsx": "javascript-react",
    ".cs": "csharp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".lua": "lua",
    ".php": "php",
}


def _detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    suffix = Path(file_path).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(suffix, suffix.lstrip(".") if suffix else "text")


def _should_exclude_dir(part: str) -> bool:
    """Check if a directory name matches any exclusion pattern."""
    return part in EXCLUDE_DIRS


def _is_excluded_path(path: Path, root: Path) -> bool:
    """Check if any parent directory of the path should be excluded."""
    try:
        relative = path.relative_to(root)
        for part in relative.parts:
            if _should_exclude_dir(part):
                return True
    except ValueError:
        return True
    return False


def read_code_projects(
    projects: List[dict],
    max_files_per_project: int = 10,
    max_file_bytes: int = 50000,
) -> dict:
    """Read local source code files from project directories.

    Args:
        projects: List of project dicts, each with keys:
            - path: Absolute or relative path to project root
            - label: Human-readable project label
            - file_patterns: Optional list of glob patterns (default is code files)
        max_files_per_project: Max files to include per project
        max_file_bytes: Max bytes to read per file

    Returns:
        dict with keys:
            - files: List of dicts with project_label, relative_path, content, language
            - errors: List of dicts with path, error
    """
    files = []
    errors = []

    for project in projects:
        project_path_str = project.get("path", "")
        project_label = project.get("label", project_path_str)
        file_patterns = project.get("file_patterns") or DEFAULT_FILE_PATTERNS

        if not project_path_str:
            errors.append({"path": project_path_str, "error": "Empty project path"})
            logger.warning("Skipping project with empty path")
            continue

        project_path = Path(project_path_str).resolve()

        if not project_path.exists():
            errors.append(
                {
                    "path": project_path_str,
                    "error": f"Project path does not exist: {project_path}",
                }
            )
            logger.warning("Project path does not exist: %s", project_path)
            continue

        if not project_path.is_dir():
            errors.append(
                {
                    "path": project_path_str,
                    "error": f"Project path is not a directory: {project_path}",
                }
            )
            logger.warning("Project path is not a directory: %s", project_path)
            continue

        # Collect matching files
        project_files = []
        for pattern in file_patterns:
            try:
                for file_path in project_path.rglob(pattern):
                    if _is_excluded_path(file_path, project_path):
                        continue
                    try:
                        file_size = file_path.stat().st_size
                    except (PermissionError, OSError):
                        logger.debug("Cannot stat file: %s", file_path)
                        continue
                    project_files.append((file_path, file_size))
            except Exception as exc:
                logger.warning("Error globbing pattern %s in %s: %s", pattern, project_path, exc)

        if not project_files:
            logger.info("No matching files found in project: %s", project_label)
            continue

        # Sort by file size (smaller first, more likely to be key files)
        project_files.sort(key=lambda x: x[1])

        # Cap at max_files_per_project
        selected = project_files[:max_files_per_project]
        logger.info(
            "Selected %d/%d files from project '%s'",
            len(selected),
            len(project_files),
            project_label,
        )

        for file_path, file_size in selected:
            try:
                relative = file_path.relative_to(project_path)
                relative_str = str(relative).replace(os.sep, "/")
            except ValueError:
                relative_str = str(file_path)

            content = ""
            try:
                raw_content = file_path.read_text(encoding="utf-8", errors="replace")
                if len(raw_content) > max_file_bytes:
                    content = raw_content[:max_file_bytes] + "\n\n... [truncated]"
                else:
                    content = raw_content
            except (PermissionError, OSError, UnicodeDecodeError) as exc:
                logger.warning("Cannot read file %s: %s", file_path, exc)
                errors.append(
                    {
                        "path": str(file_path),
                        "error": f"Cannot read file: {exc}",
                    }
                )
                continue

            language = _detect_language(relative_str)

            files.append(
                {
                    "project_label": project_label,
                    "relative_path": relative_str,
                    "content": content,
                    "language": language,
                }
            )

    return {"files": files, "errors": errors if errors else None}
