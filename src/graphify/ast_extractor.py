"""
Deterministic structural extraction from Python code using tree-sitter.
Outputs JSON nodes+edges compatible with the graphify extraction schema.

Usage:
    python -m graphify.ast_extractor file1.py [file2.py ...]
    python -m graphify.ast_extractor ./src/
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path


def _make_id(*parts: str) -> str:
    """Build a stable node ID from one or more name parts."""
    combined = "_".join(p.strip("_.") for p in parts if p)
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", combined)
    return cleaned.strip("_").lower()


def extract_python(path: Path) -> dict:
    """Extract classes, functions, and imports from a .py file via tree-sitter AST."""
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-python not installed"}

    try:
        language = Language(tspython.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int) -> None:
        # Only add edge if both endpoints exist or src is the file node
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    # File-level node — stable ID based on stem only
    file_nid = _make_id(stem)
    add_node(file_nid, path.name, 1)

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "import_statement":
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    raw = source[child.start_byte:child.end_byte].decode()
                    module_name = raw.split(" as ")[0].strip().lstrip(".")
                    tgt_nid = _make_id(module_name)
                    add_edge(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
            return

        if t == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            if module_node:
                raw = source[module_node.start_byte:module_node.end_byte].decode().lstrip(".")
                tgt_nid = _make_id(raw)
                add_edge(file_nid, tgt_nid, "imports_from", node.start_point[0] + 1)
            return

        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            class_name = source[name_node.start_byte:name_node.end_byte].decode()
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            add_node(class_nid, class_name, line)
            add_edge(file_nid, class_nid, "contains", line)

            # Inheritance
            args = node.child_by_field_name("superclasses")
            if args:
                for arg in args.children:
                    if arg.type == "identifier":
                        base = source[arg.start_byte:arg.end_byte].decode()
                        base_nid = _make_id(stem, base)
                        add_edge(class_nid, base_nid, "inherits", line)

            # Walk class body for methods
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            func_name = source[name_node.start_byte:name_node.end_byte].decode()
            line = node.start_point[0] + 1
            if parent_class_nid:
                func_nid = _make_id(parent_class_nid, func_name)
                add_node(func_nid, f".{func_name}()", line)
                add_edge(parent_class_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
            return

        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    # Post-process: remove edges whose source or target was never added as a node
    # (dangling import edges pointing to external libraries are fine to keep,
    #  but edges between internal entities must be valid)
    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        # Keep if both endpoints are known, OR if it's an import edge (tgt may be external)
        if src in valid_ids and (tgt in valid_ids or edge["relation"] in ("imports", "imports_from")):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges}


def extract(paths: list[Path]) -> dict:
    """Extract AST nodes and edges from a list of code files."""
    all_nodes: list[dict] = []
    all_edges: list[dict] = []

    for path in paths:
        if path.suffix == ".py":
            result = extract_python(path)
            all_nodes.extend(result.get("nodes", []))
            all_edges.extend(result.get("edges", []))

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def collect_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*.py")
                  if not any(part.startswith(".") for part in p.parts))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m graphify.ast_extractor <file_or_dir> ...", file=sys.stderr)
        sys.exit(1)

    paths: list[Path] = []
    for arg in sys.argv[1:]:
        paths.extend(collect_files(Path(arg)))

    result = extract(paths)
    print(json.dumps(result, indent=2))
