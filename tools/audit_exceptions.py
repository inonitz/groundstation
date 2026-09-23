#!/usr/bin/env python3
"""List every except handler and raise statement under a directory (stdlib ast; no install needed).

The harden2 exception rule: our code raises nothing, die() on a fatal invariant, and try/except only
wraps a third-party throw. Run this to see what is left:

    python3 /root/groundstation/tools/audit_exceptions.py /root/groundstation/projects/integration_harden2
"""
import ast
import os
import sys


def _handler_type(node):
    if node.type is None:
        return "BARE"
    return ast.unparse(node.type)


def _raise_type(node):
    if node.exc is None:
        return "re-raise"
    return ast.unparse(node.exc.func if isinstance(node.exc, ast.Call) else node.exc)


def scan(root):
    """-> (handlers, raises): lists of (relative_path, line, type_text)."""
    handlers, raises = [], []
    for dirpath, _dirs, files in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), path)
            rel = os.path.relpath(path, root)
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    handlers.append((rel, node.lineno, _handler_type(node)))
                elif isinstance(node, ast.Raise):
                    raises.append((rel, node.lineno, _raise_type(node)))
    return handlers, raises


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    handlers, raises = scan(root)
    print(f"except handlers: {len(handlers)}   raise statements: {len(raises)}")
    for rel, line, kind in sorted(handlers):
        print(f"  except {kind:<40} {rel}:{line}")
    for rel, line, kind in sorted(raises):
        print(f"  raise  {kind:<40} {rel}:{line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
