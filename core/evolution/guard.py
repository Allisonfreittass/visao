"""Fixed scope for autonomous patches. This controller is not model-editable."""

import ast
import difflib
import hashlib
from pathlib import Path

ALLOWED = {
    "core/study/strategy.py": ("candidate_queries", ["query", "topic"]),
    "core/conversation/style.py": ("guidance", []),
}
MAX_CHANGED_LINES = 100
_CALLS = {"dict", "list", "set", "len", "str", "sorted"}
_METHODS = {
    "strip",
    "lower",
    "casefold",
    "split",
    "replace",
    "join",
    "startswith",
    "endswith",
    "removeprefix",
    "removesuffix",
    "fromkeys",
}
_NODES = {
    ast.Module,
    ast.Expr,
    ast.Constant,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Return,
    ast.Assign,
    ast.AnnAssign,
    ast.If,
    ast.IfExp,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.comprehension,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Call,
    ast.Attribute,
    ast.keyword,
    ast.Subscript,
    ast.Slice,
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Not,
    ast.USub,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
}


def digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def validate_source(path: str, content: str) -> None:
    if path not in ALLOWED or not isinstance(content, str) or len(content) > 12_000:
        raise ValueError("outside_scope")
    tree = ast.parse(content)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    expected, args = ALLOWED[path]
    if len(functions) != 1 or functions[0].name != expected:
        raise ValueError("function_contract")
    fn = functions[0]
    if (
        [a.arg for a in fn.args.args] != args
        or fn.decorator_list
        or fn.args.defaults
        or fn.args.kwonlyargs
        or fn.args.posonlyargs
        or fn.args.vararg
        or fn.args.kwarg
    ):
        raise ValueError("function_contract")
    if any(
        n is not fn
        and not (
            isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        )
        for n in tree.body
    ):
        raise ValueError("module_statements")
    nodes = list(ast.walk(tree))
    if len(nodes) > 500:
        raise ValueError("too_complex")
    for node in nodes:
        if type(node) not in _NODES:
            raise ValueError("unsupported_operation")
        if isinstance(node, ast.FunctionDef) and node is not fn:
            raise ValueError("nested_function")
        if isinstance(node, ast.Name) and "__" in node.id:
            raise ValueError("private_name")
        if isinstance(node, ast.Attribute) and node.attr not in _METHODS:
            raise ValueError("unsupported_attribute")
        if isinstance(node, ast.Call):
            target = node.func
            if not (
                (isinstance(target, ast.Name) and target.id in _CALLS)
                or (isinstance(target, ast.Attribute) and target.attr in _METHODS)
            ):
                raise ValueError("unsupported_call")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and len(node.value) > 4000:
                raise ValueError("large_literal")
            if type(node.value) is int and abs(node.value) > 10:
                raise ValueError("large_number")
    # Communication guidance is a literal only; no access to runtime state.
    if not args and not (
        len(fn.body) == 1
        and isinstance(fn.body[0], ast.Return)
        and isinstance(fn.body[0].value, ast.Constant)
        and isinstance(fn.body[0].value.value, str)
    ):
        raise ValueError("style_must_be_literal")


def validate_snapshot(files: dict) -> None:
    if set(files) != set(ALLOWED):
        raise ValueError("snapshot_scope")
    for path, item in files.items():
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            raise ValueError("invalid_snapshot")
        if item.get("sha256") != digest(item["content"]):
            raise ValueError("snapshot_hash")
        validate_source(path, item["content"])


def validate_patch(snapshot: dict, proposal: dict) -> list[dict]:
    validate_snapshot(snapshot)
    if proposal.get("change") is not True:
        return []
    summary = proposal.get("summary")
    reason = proposal.get("reason")
    if not isinstance(summary, str) or not 5 <= len(summary) <= 160 or "\n" in summary:
        raise ValueError("invalid_summary")
    if not isinstance(reason, str) or not 10 <= len(reason) <= 1000:
        raise ValueError("invalid_reason")
    files = proposal.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 2:
        raise ValueError("invalid_patch")
    changes, seen, changed_lines = [], set(), 0
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("invalid_patch")
        path, content = item.get("path"), item.get("content")
        if not isinstance(path, str) or path in seen:
            raise ValueError("invalid_path")
        seen.add(path)
        validate_source(path, content)
        previous = snapshot[path]["content"]
        if previous == content:
            raise ValueError("unchanged_file")
        diff = list(difflib.unified_diff(previous.splitlines(), content.splitlines()))
        changed_lines += sum(line.startswith(("+", "-")) for line in diff[2:])
        changes.append(
            {
                "path": path,
                "content": content,
                "sha256": digest(content),
                "previous_sha256": digest(previous),
            }
        )
    if changed_lines > MAX_CHANGED_LINES:
        raise ValueError("patch_too_large")
    return changes


def snapshot(root: Path) -> dict:
    result = {}
    for path in ALLOWED:
        target = root / path
        if target.is_symlink() or target.resolve().parent != (root / path).parent.resolve():
            raise ValueError("symlink")
        content = target.read_text()
        result[path] = {"content": content, "sha256": digest(content)}
    validate_snapshot(result)
    return result
