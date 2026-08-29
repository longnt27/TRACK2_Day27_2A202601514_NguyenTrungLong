from __future__ import annotations

import json
from collections import deque
from pathlib import Path


def load_graph(path: str | Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload["dataset_lineage"] if "dataset_lineage" in payload else payload


def _bfs_downstream(graph: dict[str, list[str]], start: str) -> list[str]:
    seen = {start}
    queue: deque[str] = deque([start])
    output: list[str] = []
    while queue:
        node = queue.popleft()
        for child in graph.get(node, []) or []:
            if child in seen:
                continue
            seen.add(child)
            output.append(child)
            queue.append(child)
    return output


def get_downstream_assets(graph: dict[str, list[str]], start: str) -> list[str]:
    """Return transitive downstream assets in deterministic BFS order."""
    return _bfs_downstream(graph, start)


def get_column_downstream(column_graph: dict[str, list[str]], start_column: str) -> list[str]:
    """Return transitive downstream columns, cycle-safe and de-duplicated."""
    return _bfs_downstream(column_graph, start_column)


def extract_dbt_dataset_graph(manifest_path: str | Path) -> dict[str, list[str]]:
    path = Path(manifest_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    child_map = manifest.get("child_map", {})
    return {parent: list(children) for parent, children in child_map.items()}
