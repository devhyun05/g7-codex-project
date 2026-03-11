from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_node_runtime() -> str | None:
    for command_name in _node_command_names():
        resolved = shutil.which(command_name)
        if resolved:
            return resolved

    for candidate in _node_candidate_paths():
        if candidate.is_file():
            return str(candidate)

    return None


def _node_command_names() -> tuple[str, ...]:
    if os.name == "nt":
        return ("node", "node.exe", "node.cmd")
    return ("node",)


def _node_candidate_paths() -> list[Path]:
    home = Path.home()
    roots = [
        os.getenv("NVM_SYMLINK"),
        os.getenv("NVM_HOME"),
        os.getenv("VOLTA_HOME"),
        os.getenv("FNM_DIR"),
        os.getenv("ProgramFiles"),
        os.getenv("ProgramFiles(x86)"),
        os.getenv("LOCALAPPDATA"),
        os.getenv("APPDATA"),
        os.getenv("ChocolateyInstall"),
        str(home / "scoop"),
    ]

    candidate_dirs: list[Path] = []
    seen: set[str] = set()

    def add_dir(raw_path: str | None, *segments: str) -> None:
        if not raw_path:
            return
        path = Path(raw_path).joinpath(*segments)
        normalized = str(path).lower()
        if normalized in seen:
            return
        seen.add(normalized)
        candidate_dirs.append(path)

    add_dir(os.getenv("ProgramFiles"), "nodejs")
    add_dir(os.getenv("ProgramFiles(x86)"), "nodejs")
    add_dir(os.getenv("LOCALAPPDATA"), "Programs", "nodejs")
    add_dir(os.getenv("APPDATA"), "nvm")
    add_dir(os.getenv("LOCALAPPDATA"), "nvm")
    add_dir(os.getenv("ChocolateyInstall"), "bin")
    add_dir(os.getenv("VOLTA_HOME"), "bin")
    add_dir(str(home), "scoop", "apps", "nodejs", "current")

    for root in roots:
        if not root:
            continue
        add_dir(root)
        add_dir(root, "bin")
        add_dir(root, "current")

    candidate_paths: list[Path] = []
    for directory in candidate_dirs:
        if os.name == "nt":
            candidate_paths.extend(
                [
                    directory / "node.exe",
                    directory / "node.cmd",
                ]
            )
        else:
            candidate_paths.append(directory / "node")

    return candidate_paths
