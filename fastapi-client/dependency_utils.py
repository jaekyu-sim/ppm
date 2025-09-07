import re
from pathlib import Path
from typing import Dict, Set

PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\.\w]+)\s+import|import\s+([\.\w]+))", re.MULTILINE)
JAVA_IMPORT_RE = re.compile(r"^\s*import\s+([\w\.]+);", re.MULTILINE)


def _find_import_paths(code: str, current_file: Path, project_root: Path) -> Set[Path]:
    """Return set of local dependency file paths for given code."""
    paths: Set[Path] = set()

    for m in PY_IMPORT_RE.finditer(code):
        mod = m.group(1) or m.group(2)
        if not mod:
            continue
        if mod.startswith("."):
            rel = mod.lstrip(".")
            levels = len(mod) - len(rel)
            base = current_file.parent
            for _ in range(max(0, levels - 1)):
                base = base.parent
            candidate = (base / rel.replace(".", "/")).with_suffix(".py")
        else:
            candidate = (project_root / mod.replace(".", "/")).with_suffix(".py")
        if candidate.exists():
            paths.add(candidate)

    for m in JAVA_IMPORT_RE.finditer(code):
        mod = m.group(1)
        candidate = (project_root / mod.replace(".", "/")).with_suffix(".java")
        if candidate.exists():
            paths.add(candidate)

    return paths


def collect_code_with_dependencies(file_path: str, project_root: str | None = None) -> Dict[str, str]:
    """Return a mapping of file paths to code including local imported modules."""
    fp = Path(file_path).resolve()
    root = Path(project_root).resolve() if project_root else fp.parent
    codes: Dict[str, str] = {}
    visited: Set[Path] = set()

    def _collect(path: Path) -> None:
        if path in visited or not path.exists():
            return
        visited.add(path)
        text = path.read_text(encoding="utf-8")
        codes[str(path)] = text
        for dep in _find_import_paths(text, path, root):
            _collect(dep)

    _collect(fp)
    return codes


def combined_code_with_dependencies(file_path: str, project_root: str | None = None) -> str:
    """Return concatenated code for file and its local dependencies."""
    codes = collect_code_with_dependencies(file_path, project_root)
    parts = []
    for path, text in codes.items():
        parts.append(f"// File: {path}\n{text}")
    return "\n\n".join(parts)