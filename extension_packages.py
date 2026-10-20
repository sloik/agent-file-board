"""Offline extension package API 1. Package integrity, bounded schemas and immutable message semantics."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

API_VERSION = "1.2.0"
MAX_PACKAGE = 4 * 1024 * 1024
MAX_FILE = 1024 * 1024
MAX_PACKAGES = 32
SAFE_INTEGER = 9007199254740991
PACKAGE_ID = re.compile(r"[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*){1,7}")
NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")
DIGEST = re.compile(r"[a-f0-9]{64}")
VERSION = re.compile(r"(0|[1-9][0-9]{0,6})\.(0|[1-9][0-9]{0,6})\.(0|[1-9][0-9]{0,6})")


class ExtensionUnavailable(ValueError):
    """Readable core message; optional retained semantic definition unavailable."""


def require(ok, message):
    if not ok:
        raise ValueError("extensions: " + message)


def text(value, limit=10000):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)


def keys(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= value.keys() and value.keys() <= set(required) | set(optional), "unexpected or missing keys")


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def parse(raw, limit=MAX_PACKAGE):
    require(isinstance(raw, bytes) and 0 < len(raw) <= limit, "JSON byte limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: require(False, "nonfinite JSON number"))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("extensions: invalid UTF-8 JSON") from exc
    # Reject escaped lone surrogates in every string, including unknown fields.
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        require(depth <= 32 and count <= 50000, "JSON structure limit")
        if isinstance(item, str):
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in item), "invalid Unicode")
        elif isinstance(item, float):
            require(math.isfinite(item), "nonfinite JSON number")
        elif isinstance(item, dict):
            pending.extend((s, depth + 1) for pair in item.items() for s in pair)
        elif isinstance(item, list):
            pending.extend((s, depth + 1) for s in item)
    return value


def version(value):
    require(isinstance(value, str) and VERSION.fullmatch(value), "expected stable numeric X.Y.Z version")
    return tuple(map(int, value.split(".")))


def constraint(value):
    keys(value, {"range"}, {"exclude"})
    require(text(value["range"], 200), "invalid version range")
    tokens = value["range"].split()
    require(1 <= len(tokens) <= 8, "range comparator limit")
    for token in tokens:
        match = re.fullmatch(r"(>=|<=|>|<|=)?(.+)", token)
        require(match is not None, "invalid comparator")
        version(match[2])
    exclusions = value.get("exclude", [])
    require(isinstance(exclusions, list) and len(exclusions) <= 32, "exclusion limit")
    for excluded in exclusions:
        version(excluded)
    require(len(set(exclusions)) == len(exclusions), "duplicate exclusions")
    return value


def supports(value, candidate):
    constraint(value)
    current = version(candidate)
    if candidate in value.get("exclude", []):
        return False
    for token in value["range"].split():
        op, target = re.fullmatch(r"(>=|<=|>|<|=)?(.+)", token).groups()
        other = version(target)
        if not {None: current == other, "=": current == other, ">=": current >= other,
                "<=": current <= other, ">": current > other, "<": current < other}[op]:
            return False
    return True


def number(value):
    return type(value) in (int, float) and abs(value) <= SAFE_INTEGER and math.isfinite(value)


def validate_schema(schema, depth=0, budget=None):
    budget = [0] if budget is None else budget
    budget[0] += 1
    require(depth <= 8 and budget[0] <= 256, "schema structure limit")
    require(isinstance(schema, dict), "schema must be an object")
    kind = schema.get("type")
    specific = {"string": {"minLength", "maxLength"}, "number": {"minimum", "maximum"},
                "integer": {"minimum", "maximum"}, "boolean": set(), "null": set(),
                "object": {"properties", "required", "additionalProperties"},
                "array": {"items", "minItems", "maxItems"}}
    require(isinstance(kind, str) and kind in specific, "unsupported schema type")
    keys(schema, {"type"}, {"nullable", "enum"} | specific[kind])
    require(type(schema.get("nullable", False)) is bool, "nullable must be boolean")
    if kind in {"string", "array"}:
        low, high, cap = ("minLength", "maxLength", 10000) if kind == "string" else ("minItems", "maxItems", 256)
        require(number(schema.get(high)) and int(schema[high]) == schema[high] and 0 <= schema[high] <= cap, "explicit bounded maximum required")
        require(number(schema.get(low, 0)) and int(schema.get(low, 0)) == schema.get(low, 0) and 0 <= schema.get(low, 0) <= schema[high], "invalid minimum")
    if kind in {"number", "integer"}:
        require(all(number(schema[k]) for k in ("minimum", "maximum") if k in schema), "numeric bounds must be finite safe numbers")
        require(schema.get("minimum", -SAFE_INTEGER) <= schema.get("maximum", SAFE_INTEGER), "inverted bounds")
    if kind == "object":
        require(isinstance(schema.get("properties"), dict) and len(schema["properties"]) <= 64 and schema.get("additionalProperties") is False, "closed bounded object required")
        required = schema.get("required", [])
        require(isinstance(required, list) and all(isinstance(x, str) for x in required) and len(set(required)) == len(required) and set(required) <= schema["properties"].keys(), "invalid required properties")
        for name, child in schema["properties"].items():
            require(NAME.fullmatch(name), "invalid property name")
            validate_schema(child, depth + 1, budget)
    if kind == "array":
        require("items" in schema, "array items required")
        validate_schema(schema["items"], depth + 1, budget)
    if "enum" in schema:
        values = schema["enum"]
        require(kind not in {"object", "array"} and isinstance(values, list) and 1 <= len(values) <= 64, "bounded scalar enum required")
        for item in values:
            _validate_value(item, {k: v for k, v in schema.items() if k != "enum"})
    return schema


def _validate_value(value, schema):
    if value is None and schema.get("nullable"):
        return
    kind = schema["type"]
    valid = {"null": value is None, "boolean": type(value) is bool,
             "number": number(value), "integer": number(value) and int(value) == value,
             "string": isinstance(value, str), "array": isinstance(value, list), "object": isinstance(value, dict)}[kind]
    require(valid, "payload type differs from schema")
    if "enum" in schema:
        require(any((type(value) is type(item) or number(value) and number(item)) and value == item for item in schema["enum"]), "payload not in enum")
    if kind == "string":
        require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value) and schema.get("minLength", 0) <= len(value) <= schema["maxLength"], "string scalar limit")
    elif kind in {"number", "integer"}:
        require(schema.get("minimum", -SAFE_INTEGER) <= value <= schema.get("maximum", SAFE_INTEGER), "payload numeric bounds")
    elif kind == "object":
        require(set(schema.get("required", [])) <= value.keys() <= schema["properties"].keys(), "payload object keys")
        for key, item in value.items():
            _validate_value(item, schema["properties"][key])
    elif kind == "array":
        require(schema.get("minItems", 0) <= len(value) <= schema["maxItems"], "payload array limit")
        for item in value:
            _validate_value(item, schema["items"])


def validate_value(value, schema):
    validate_schema(schema)
    _validate_value(value, schema)


def safe_name(value):
    require(isinstance(value, str) and len(value) <= 160 and all(NAME.fullmatch(x.split(".")[0]) and re.fullmatch(r"[a-z0-9.-]+", x) and ".." not in x for x in value.split("/")), "unsafe entry name")
    require(not value.startswith("/") and "\\" not in value, "unsafe entry name")
    return value


def decode_package(raw):
    package = parse(raw)
    keys(package, {"format", "id", "version", "name", "compatibility", "capabilities", "files"}, {"description", "publisher", "convention", "ui"})
    require(number(package["format"]) and package["format"] == 1, "unsupported package format")
    require(isinstance(package["id"], str) and len(package["id"]) <= 128 and PACKAGE_ID.fullmatch(package["id"]), "invalid package namespace")
    version(package["version"])
    require(text(package["name"], 120), "invalid name")
    for field in ("publisher", "description"):
        if field in package:
            require(text(package[field], 1000), "invalid " + field)
    keys(package["compatibility"], {"convention", "api"})
    for item in package["compatibility"].values():
        constraint(item)
    caps = package["capabilities"]
    require(isinstance(caps, list) and all(isinstance(x, str) and x in {"render", "propose-reply", "read-state", "refresh"} for x in caps) and len(set(caps)) == len(caps), "unsupported capabilities; request additions through GitHub")
    if "refresh" in caps:
        require(supports(package["compatibility"]["api"], "1.2.0"), "refresh requires SDK 1.2 compatibility")
    require("convention" in package or "ui" in package, "at least one facet required")
    require(isinstance(package["files"], dict) and 1 <= len(package["files"]) <= 64, "file count limit")
    files = {}
    for name, entry in package["files"].items():
        safe_name(name)
        keys(entry, {"encoding", "data", "sha256"})
        require(isinstance(entry["data"], str) and isinstance(entry["encoding"], str) and entry["encoding"] in {"utf-8", "base64"}, "invalid file encoding")
        try:
            decoded = entry["data"].encode("utf-8") if entry["encoding"] == "utf-8" else base64.b64decode(entry["data"], validate=True)
        except (ValueError, UnicodeError) as exc:
            raise ValueError("extensions: invalid file bytes") from exc
        if entry["encoding"] == "base64":
            require(base64.b64encode(decoded).decode() == entry["data"], "noncanonical base64")
        require(len(decoded) <= MAX_FILE and isinstance(entry["sha256"], str) and DIGEST.fullmatch(entry["sha256"]) and hashlib.sha256(decoded).hexdigest() == entry["sha256"], "entry size/hash mismatch")
        files[name] = decoded

    def entry(name, as_json=False):
        require(isinstance(name, str) and name in files, "missing package entry")
        return parse(files[name], MAX_FILE) if as_json else files[name].decode("utf-8")

    contracts = []
    if "convention" in package:
        keys(package["convention"], {"contracts"})
        declarations = package["convention"]["contracts"]
        require(isinstance(declarations, list) and 1 <= len(declarations) <= 16, "contract count limit")
        for contract in declarations:
            keys(contract, {"id", "version", "schema", "guidance", "examples"}, {"answerSchema"})
            require(isinstance(contract["id"], str) and contract["id"].count("/") == 1 and contract["id"].startswith(package["id"] + "/") and NAME.fullmatch(contract["id"].split("/")[-1]), "contract must use package namespace")
            version(contract["version"])
            schema = validate_schema(entry(contract["schema"], True))
            guidance = entry(contract["guidance"])
            require(bool(guidance.strip()) and len(guidance) <= 20000, "guidance required")
            examples = contract["examples"]
            require(isinstance(examples, list) and 1 <= len(examples) <= 8 and all(isinstance(x, str) for x in examples), "example count limit")
            for example in examples:
                validate_value(entry(example, True), schema)
            if "answerSchema" in contract:
                validate_schema(entry(contract["answerSchema"], True))
            refs = [contract["schema"], contract["guidance"]] + ([contract["answerSchema"]] if "answerSchema" in contract else []) + examples
            fingerprint = "\n".join([contract["id"], contract["version"]] + [package["files"][ref]["sha256"] for ref in refs])
            contracts.append({**contract, "digest": hashlib.sha256(fingerprint.encode()).hexdigest()})
        require(len({(c["id"], c["version"]) for c in contracts}) == len(contracts), "duplicate contract declaration")
    if "ui" in package:
        keys(package["ui"], {"renderers"})
        renderers = package["ui"]["renderers"]
        require(isinstance(renderers, list) and 1 <= len(renderers) <= 16 and "render" in caps, "UI requires render capability and bounded renderer list")
        seen = set()
        for renderer in renderers:
            keys(renderer, {"id", "mode", "entry", "contracts"}, {"refresh"})
            if "refresh" in renderer:
                require("refresh" in caps, "refresh capability required")
                keys(renderer["refresh"], {"intervalSeconds"})
                interval = renderer["refresh"]["intervalSeconds"]
                require(number(interval) and int(interval) == interval and 30 <= interval <= 86400, "refresh interval must be an integer from 30 through 86400")
            require(isinstance(renderer["id"], str) and NAME.fullmatch(renderer["id"]) and renderer["id"] not in seen, "invalid/duplicate renderer ID")
            seen.add(renderer["id"])
            require(isinstance(renderer["mode"], str) and renderer["mode"] in {"declarative", "worker"}, "unsupported renderer mode")
            require(bool(entry(renderer["entry"]).strip()), "renderer entry required")
            targets = renderer["contracts"]
            require(isinstance(targets, list) and 1 <= len(targets) <= 16, "renderer target limit")
            for target in targets:
                keys(target, {"id", "versions"})
                require(text(target["id"], 200) and ":" not in target["id"], "invalid target ID")
                constraint(target["versions"])
    if "refresh" in caps:
        require(any("refresh" in r for r in package.get("ui", {}).get("renderers", [])), "refresh capability requires a renderer declaration")
    return {"artifact": hashlib.sha256(raw).hexdigest(), "package": package, "contracts": contracts, "files": files}


def read_file(path, limit=MAX_PACKAGE):
    path = Path(path)
    for parent in [path, *path.parents]:
        require(not parent.is_symlink(), "symlink paths are not allowed")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, "expected bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit, "file byte limit")
        return raw
    finally:
        os.close(fd)


def board_dir(root):
    board = Path(root).resolve() / ".agent-board"
    require(board.is_dir() and not board.is_symlink(), "expected native board directory")
    config = parse(read_file(board / "config.json"))
    require(isinstance(config, dict) and "board" in config, "invalid board config")
    return board


def convention_version(board):
    match = re.search(r"^Version: (.+)$", read_file(board / "CONVENTION.md").decode("utf-8"), re.M)
    require(match is not None, "board convention version unavailable")
    version(match[1])
    return match[1]


def extension_dir(board, create=False):
    path = board / "extensions"
    require(not path.is_symlink(), "extensions directory cannot be a symlink")
    if create:
        path.mkdir(exist_ok=True)
    require(not path.exists() or path.is_dir(), "invalid extensions directory")
    return path


def registry(path):
    if not path.exists():
        require(not path.is_symlink(), "registry symlink")
        return {"format": 1, "packages": []}
    result = parse(read_file(path, 65536), 65536)
    keys(result, {"format", "packages"})
    require(number(result["format"]) and result["format"] == 1 and isinstance(result["packages"], list) and len(result["packages"]) <= MAX_PACKAGES, "invalid registry")
    seen = set()
    for row in result["packages"]:
        keys(row, {"artifact", "enabled"})
        require(isinstance(row["artifact"], str) and DIGEST.fullmatch(row["artifact"]) and type(row["enabled"]) is bool and row["artifact"] not in seen, "invalid registry row")
        seen.add(row["artifact"])
    return result


def snapshot(directory, digest):
    require(isinstance(digest, str) and DIGEST.fullmatch(digest), "invalid artifact digest")
    decoded = decode_package(read_file(directory / "packages" / digest / "package.afb-plugin.json"))
    require(decoded["artifact"] == digest, "artifact digest mismatch")
    return decoded


def api_compatible(package):
    rule = package["compatibility"]["api"]
    caps = package["capabilities"]
    return (supports(rule, API_VERSION)
            or ("refresh" not in caps and supports(rule, "1.1.0"))
            or ("refresh" not in caps and "read-state" not in caps and supports(rule, "1.0.0")))


def catalog(root):
    board = board_dir(root)
    directory = extension_dir(board)
    board_version = convention_version(board)
    result = {"format": 1, "api": API_VERSION, "convention": board_version, "packages": []}
    for row in registry(directory / "registry.json")["packages"]:
        item = dict(row)
        try:
            decoded = snapshot(directory, row["artifact"])
            package = decoded["package"]
            compatible = supports(package["compatibility"]["convention"], board_version) and api_compatible(package)
            item.update(id=package["id"], version=package["version"], name=package["name"],
                        state="disabled" if not row["enabled"] else "available" if compatible else "incompatible",
                        contracts=decoded["contracts"], renderers=package.get("ui", {}).get("renderers", []),
                        execution="viewer-local-approval-required")
        except (ValueError, OSError, UnicodeError) as exc:
            item.update(state="unavailable", error=str(exc))
        result["packages"].append(item)
    # No same-version contract may resolve to different meanings.
    identities = {}
    releases = {}
    for item in result["packages"]:
        if "id" in item:
            releases.setdefault((item["id"], item["version"]), set()).add(item["artifact"])
        for contract in item.get("contracts", []):
            key = (contract["id"], contract["version"])
            identities.setdefault(key, set()).add(contract["digest"])
    for item in result["packages"]:
        if ("id" in item and len(releases[(item["id"], item["version"])]) > 1) or any(len(identities[(c["id"], c["version"])]) > 1 for c in item.get("contracts", [])):
            item["state"] = "conflict"
    return result


@contextmanager
def mutation_lock(directory):
    lock = directory / ".registry-lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        yield
    finally:
        os.close(fd)
        lock.unlink()


def atomic_json(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    require(not path.is_symlink(), "cannot replace symlink metadata")
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(root, artifact):
    raw = read_file(Path(artifact).resolve())
    decoded = decode_package(raw)
    board = board_dir(root)
    directory = extension_dir(board, True)
    package = decoded["package"]
    require(supports(package["compatibility"]["convention"], convention_version(board)) and api_compatible(package), "package is incompatible")
    with mutation_lock(directory):
        current = registry(directory / "registry.json")
        for row in current["packages"]:
            prior = snapshot(directory, row["artifact"])
            old = prior["package"]
            require((old["id"], old["version"]) != (package["id"], package["version"]) or prior["artifact"] == decoded["artifact"], "package ID/version conflicts with retained bytes")
            for first in prior["contracts"]:
                for second in decoded["contracts"]:
                    require((first["id"], first["version"]) != (second["id"], second["version"]) or first["digest"] == second["digest"], "contract ID/version conflicts with retained meaning")
        exists = any(row["artifact"] == decoded["artifact"] for row in current["packages"])
        require(exists or len(current["packages"]) < MAX_PACKAGES, "retained package limit")
        packages = directory / "packages"
        require(not packages.is_symlink(), "package directory symlink")
        packages.mkdir(exist_ok=True)
        destination = packages / decoded["artifact"]
        require(not destination.is_symlink(), "snapshot directory symlink")
        destination.mkdir(exist_ok=True)
        target = destination / "package.afb-plugin.json"
        if target.exists() or target.is_symlink():
            require(read_file(target) == raw, "retained snapshot differs")
        else:
            fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=destination)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temporary, target, follow_symlinks=False)
            finally:
                os.unlink(temporary)
        if not exists:
            current["packages"].append({"artifact": decoded["artifact"], "enabled": True})
        else:
            for row in current["packages"]:
                if row["artifact"] == decoded["artifact"]:
                    row["enabled"] = True
        atomic_json(directory / "registry.json", current)
    # Catalog reads are derived from verified artifacts, never trusted cache data.
    return {"artifact": decoded["artifact"], "id": package["id"], "version": package["version"], "enabled": True, "codeApproved": False}


def disable(root, digest):
    directory = extension_dir(board_dir(root))
    with mutation_lock(directory):
        current = registry(directory / "registry.json")
        require(any(row["artifact"] == digest for row in current["packages"]), "artifact not registered")
        for row in current["packages"]:
            if row["artifact"] == digest:
                row["enabled"] = False
        atomic_json(directory / "registry.json", current)
    return {"artifact": digest, "enabled": False}


def command(args):
    require(1024 <= args.max_bytes <= MAX_PACKAGE, "--max-bytes must be 1024..4194304")
    action = args.extension_action
    if action == "inspect":
        decoded = decode_package(read_file(Path(args.artifact).resolve()))
        package = decoded["package"]
        result = {k: v for k, v in package.items() if k != "files"}
        result.update(artifact=decoded["artifact"], files=list(decoded["files"]), execution="never")
    elif action == "install":
        result = install(args.path, args.artifact)
    elif action == "disable":
        result = disable(args.path, args.artifact)
    elif action == "list":
        result = catalog(args.path)
    elif action == "envelope":
        board = board_dir(args.path)
        decoded = snapshot(extension_dir(board), args.artifact)
        contract = next((c for c in decoded["contracts"] if c["id"] == args.contract and c["version"] == args.contract_version), None)
        require(contract is not None, "contract not found")
        result = {"version": 1, "package": args.artifact, "contract": contract["id"], "contractVersion": contract["version"], "contractDigest": contract["digest"], "data": parse(read_file(Path(args.data_file).resolve(), 65536), 65536)}
        if args.renderer_package or args.renderer:
            require(args.renderer_package and args.renderer, "both renderer arguments required")
            result["renderer"] = {"package": args.renderer_package, "id": args.renderer}
        resolve(board, result, active=True)
    else:
        result = catalog(args.path)
        selected = next((item for item in result["packages"] if item["artifact"] == args.artifact), None)
        require(selected is not None, "artifact not registered")
        result = dict(selected)
        if "id" in selected:
            decoded = snapshot(extension_dir(board_dir(args.path)), args.artifact)
            result["definitions"] = [{**contract, "schemaValue": parse(decoded["files"][contract["schema"]]),
                                       "guidanceText": decoded["files"][contract["guidance"]].decode("utf-8"),
                                       "exampleValues": [parse(decoded["files"][name]) for name in contract["examples"]],
                                       **({"answerSchemaValue": parse(decoded["files"][contract["answerSchema"]])} if "answerSchema" in contract else {})}
                                      for contract in decoded["contracts"]]
    output = json.dumps(result, ensure_ascii=False, indent=2)
    require(len(output.encode("utf-8")) <= args.max_bytes, "output exceeds --max-bytes (1024..4194304); inspect/describe exact packages on demand")
    print(output)
    return 0


def add_parser(commands):
    parent = commands.add_parser("extensions", help="Offline packages and agent contracts; never executes renderer code")
    actions = parent.add_subparsers(dest="extension_action", required=True)
    for action in ("inspect", "install", "list", "describe", "disable", "envelope"):
        sub = actions.add_parser(action)
        if action != "list":
            sub.add_argument("artifact", help="Package filename for inspect/install; SHA256 for describe/disable")
        sub.add_argument("--path", default=".")
        sub.add_argument("--max-bytes", type=int, default=16384)
        if action == "envelope":
            sub.add_argument("--contract", required=True)
            sub.add_argument("--contract-version", default="1.0.0")
            sub.add_argument("--data-file", required=True)
            sub.add_argument("--renderer-package")
            sub.add_argument("--renderer")
        sub.set_defaults(func=command)


# Wire envelope version is independent of the package format and SDK API.
def envelope(value, answer=False):
    required = {"version", "package", "contract", "contractVersion", "contractDigest", "data"}
    keys(value, required | ({"source"} if answer else set()), set() if answer else {"renderer"})
    require(number(value["version"]) and value["version"] == 1, "unsupported envelope version")
    for key in ("package", "contractDigest"):
        require(isinstance(value[key], str) and DIGEST.fullmatch(value[key]), "invalid envelope digest")
    require(isinstance(value["contract"], str) and re.fullmatch(PACKAGE_ID.pattern + r"/" + NAME.pattern, value["contract"]), "invalid contract ID")
    version(value["contractVersion"])
    require(len(json.dumps(value, ensure_ascii=False).encode("utf-8")) <= 65536, "envelope byte limit")
    if answer:
        keys(value["source"], {"message", "sha256"})
        source = value["source"]
        require(isinstance(source["message"], str) and re.fullmatch(r"(?:rooms|direct)/[a-z0-9-]+/[a-zA-Z0-9_.-]+\.txt", source["message"]), "invalid source path")
        require(isinstance(source["sha256"], str) and DIGEST.fullmatch(source["sha256"]), "invalid source digest")
    elif value.get("renderer") is not None:
        keys(value["renderer"], {"package", "id"})
        require(isinstance(value["renderer"]["package"], str) and DIGEST.fullmatch(value["renderer"]["package"]) and isinstance(value["renderer"]["id"], str) and NAME.fullmatch(value["renderer"]["id"]), "invalid renderer reference")
    return value


def resolve(board, value, active=False, answer=False):
    envelope(value, answer)
    try:
        directory = extension_dir(board)
        rows = registry(directory / "registry.json")["packages"]
        states = {item["artifact"]: item["state"] for item in catalog(board.parent)["packages"]} if active else {}
    except (ValueError, OSError, UnicodeError) as exc:
        raise ExtensionUnavailable("extensions: unavailable registry: " + str(exc)) from exc
    def retained(digest):
        row = next((row for row in rows if row["artifact"] == digest), None)
        if row is None:
            raise ExtensionUnavailable("extensions: unavailable: package not retained in board")
        try:
            decoded = snapshot(directory, digest)
        except (ValueError, OSError, UnicodeError) as exc:
            raise ExtensionUnavailable("extensions: unavailable snapshot: " + str(exc)) from exc
        if active:
            require(row["enabled"], "package disabled for new messages")
            require(states.get(digest) == "available", "package incompatible, unavailable or conflicting")
            require(supports(decoded["package"]["compatibility"]["convention"], convention_version(board)) and api_compatible(decoded["package"]), "package incompatible for new messages")
        return decoded
    decoded = retained(value["package"])
    contract = next((c for c in decoded["contracts"] if c["id"] == value["contract"] and c["version"] == value["contractVersion"] and c["digest"] == value["contractDigest"]), None)
    require(contract is not None, "contract identity differs from retained meaning")
    field = "answerSchema" if answer else "schema"
    require(field in contract, "contract does not accept answers")
    validate_value(value["data"], parse(decoded["files"][contract[field]]))
    if not answer and value.get("renderer"):
        ref = value["renderer"]
        visual = retained(ref["package"])
        renderer = next((r for r in visual["package"].get("ui", {}).get("renderers", []) if r["id"] == ref["id"]), None)
        require(renderer is not None and any(t["id"] == contract["id"] and supports(t["versions"], contract["version"]) for t in renderer["contracts"]), "renderer does not support contract")
    return decoded, contract


def validate_message(board, path, headers, body, active=False):
    names = [key for key in ("EXTENSION", "EXTENSION-ANSWER") if key in headers]
    if not names:
        return
    require(len(names) == 1 and not any(key in headers for key in ("UI", "QUESTION", "ANSWER")), "only one structured message kind allowed")
    require(bool(body.strip()), "readable body fallback required")
    if active:
        require(version(convention_version(board)) >= (2, 5, 0), "upgrade board convention to 2.5.0 before extension posts")
    answer = names[0] == "EXTENSION-ANSWER"
    value = parse(headers[names[0]].encode("utf-8"), 65536)
    envelope(value, answer)
    if answer:
        source = board / value["source"]["message"]
        require(source.parent == path.parent and source.name == headers.get("REPLY-TO") and source != path, "answer source must be reply target in same conversation")
        raw = read_file(source, 4 * 1024 * 1024)
        require(hashlib.sha256(raw).hexdigest() == value["source"]["sha256"], "stale answer source")
        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        head, sep, source_body = text.partition("\n---\n")
        require(bool(sep), "invalid source separator")
        original = pairs([line.split(": ", 1) for line in head.splitlines() if ": " in line])
        require("EXTENSION" in original and not any(k in original for k in ("EXTENSION-ANSWER", "UI", "QUESTION", "ANSWER")), "source is not an extension request")
        request = parse(original["EXTENSION"].encode("utf-8"), 65536)
        envelope(request)
        require(bool(source_body.strip()) and original.get("THREAD", "").split("-")[0] == headers.get("THREAD", "").split("-")[0] and original.get("SCOPE") == headers.get("SCOPE") and original.get("FROM") == headers.get("TO"), "answer source routing differs")
        require(all(value[k] == request[k] for k in ("package", "contract", "contractVersion", "contractDigest")), "answer contract differs from source")
    resolve(board, value, active, answer)
    if answer:
        resolve(board, request, False)
