"""The OCPI handshake Worker's settings and the project facts it copies (ocpi/, ADR 0025).

The Worker's behaviour is tested in tests/js/ocpi.test.js.
"""

import re
import tomllib

from adapters import http
from pipeline import project
from pipeline.registry import ROOT, load_registry

OCPI = ROOT / "ocpi"
WORKER = (OCPI / "worker.js").read_text(encoding="utf-8")
CODE = re.sub(r"(?m)^\s*//.*$", "", WORKER)  # without whole-line comments
SETTINGS = tomllib.loads((OCPI / "wrangler.toml").read_text(encoding="utf-8"))


def constant(name: str) -> str:
    """The value of a one-line `export const` in worker.js, as written."""
    found = re.search(rf"^export const {name} = (.+);$", WORKER, re.MULTILINE)
    assert found, f"ocpi/worker.js must export {name} on one line"
    return found.group(1)


def text_constant(name: str) -> str:
    value = constant(name)
    assert re.fullmatch(r'"[^"\\]*"', value), f"{name} must be a plain string"
    return value[1:-1]


def paths() -> dict[str, str]:
    block = re.search(r"^export const PATHS = \{\n(.*?)^\};$", WORKER, re.MULTILINE | re.DOTALL)
    assert block, "ocpi/worker.js must export PATHS"
    return dict(re.findall(r'^ {2}(\w+): "([^"]+)",$', block.group(1), re.MULTILINE))


def test_the_worker_settings_deploy_one_durable_object_and_nothing_else():
    assert SETTINGS["name"] == "oevm-ocpi"
    assert (OCPI / SETTINGS["main"]).is_file()
    assert SETTINGS["compatibility_flags"] == ["enable_request_signal"]
    assert SETTINGS["workers_dev"] is True
    assert SETTINGS["preview_urls"] is False
    assert SETTINGS["observability"]["enabled"] is False
    assert SETTINGS["durable_objects"]["bindings"] == [
        {"name": "CONNECTION", "class_name": "OcpiConnection"}
    ]
    assert SETTINGS["migrations"] == [{"tag": "v1", "new_sqlite_classes": ["OcpiConnection"]}]
    unwanted = {
        "vars",
        "routes",
        "route",
        "triggers",
        "kv_namespaces",
        "secrets",
        "keep_vars",
        "exports",
        "d1_databases",
        "r2_buckets",
        "services",
        "tail_consumers",
    }
    assert not unwanted & SETTINGS.keys(), "secrets stay in Cloudflare; no timer, store or route"


def test_the_class_binding_and_storage_match_the_code():
    binding = SETTINGS["durable_objects"]["bindings"][0]
    classes = re.findall(r"^export class (\w+) extends DurableObject \{$", CODE, re.MULTILINE)
    assert classes == [binding["class_name"]] == ["OcpiConnection"]
    imports = re.findall(r"^import .*$", CODE, re.MULTILINE)
    assert imports == ['import { DurableObject } from "cloudflare:workers";']
    # The one object is found by its neutral name, with the long-supported calls.
    assert f"env.{binding['name']}.idFromName(OBJECT_NAME)" in CODE
    assert f"env.{binding['name']}.get(" in CODE
    assert "getByName" not in CODE
    # Synchronous storage only, so no read and its write can interleave with another request.
    assert "this.ctx.storage.kv.get(STORAGE_KEY)" in CODE
    assert "this.ctx.storage.kv.put(STORAGE_KEY" in CODE
    for asynchronous in ("this.ctx.storage.get(", "this.ctx.storage.put(", "blockConcurrencyWhile"):
        assert asynchronous not in CODE, asynchronous


def test_fetch_is_the_only_public_method_of_the_durable_object():
    # Another Worker on the same Cloudflare account that binds to the class can call its public
    # methods over RPC, so every member but the constructor and fetch is private (#name).
    found = re.search(
        r"^export class OcpiConnection extends DurableObject \{\n(.*?)^\}$",
        CODE,
        re.MULTILINE | re.DOTALL,
    )
    assert found, "ocpi/worker.js must define OcpiConnection"
    # Members start two spaces in, and the methods' bodies further in. Anything else at that
    # depth (a field, a getter or setter, a static member, a computed name) fails here.
    lines = [
        line
        for line in found.group(1).splitlines()
        if re.match(r" {2}\S", line) and line.strip() != "}"
    ]
    member = re.compile(r" {2}(?:async )?(#?[A-Za-z_$][\w$]*)\(.*\) \{")
    names = []
    for line in lines:
        matched = member.fullmatch(line)
        assert matched, f"not a plain method: {line.strip()}"
        names.append(matched.group(1))
    assert [name for name in names if not name.startswith("#")] == ["constructor", "fetch"]
    assert {"#load", "#save", "#handOut", "#readPeer", "#callPeer"} <= set(names)


def test_the_worker_sends_the_project_user_agent():
    assert f'export const USER_AGENT = "{http.USER_AGENT}";' in WORKER


def test_the_worker_keeps_the_operators_gap():
    gap_ms = constant("GAP_MS")
    assert re.fullmatch(r"\d[\d_]*", gap_ms), gap_ms
    assert int(gap_ms.replace("_", "")) / 1000 >= http.required_gap(load_registry()["tesla"])


def test_no_operator_name_in_the_workers_names():
    routes = paths()
    assert set(routes) == {"versions", "details", "credentials", "connection"}
    binding = SETTINGS["durable_objects"]["bindings"][0]
    names = [
        SETTINGS["name"],
        binding["name"],
        binding["class_name"],
        text_constant("OBJECT_NAME"),
        text_constant("STORAGE_KEY"),
        *(segment for route in routes.values() for segment in route.split("/") if segment),
    ]
    for operator_id, config in load_registry().items():
        words = {operator_id, operator_id.replace("_", "-"), config.display_name.lower()}
        for name in names:
            for word in words:
                assert word not in name.lower(), f"{name} contains {word}"


def test_the_credentials_name_only_the_project():
    assert f'name: "{project.NAME}"' in WORKER
    assert 'role: "NSP"' in WORKER
    assert 'country_code: "GB"' in WORKER
    party_id = re.search(r'party_id: "([A-Z0-9]{3})"', WORKER)
    assert party_id, "PARTY.party_id must be three capital letters or digits"
    assert party_id.group(1) != "TES", "never an operator's own example"
    website = re.search(r'website: "(https://[^"]+)"', WORKER)
    assert website, "PARTY.website must be an https address"
    assert website.group(1) in (ROOT / "README.md").read_text(encoding="utf-8")
    assert '"logo"' not in WORKER
    assert not re.search(r"\blogo\b", CODE)


def test_the_worker_never_logs_and_makes_one_kind_of_outbound_call():
    assert "console." not in WORKER
    # One call to the other party's server; the object's and the handler's own fetch methods
    # and the call that hands a request to the object do not count.
    assert len(re.findall(r"(?<![.\w])(?<!async )fetch\(", CODE)) == 1
    # Every other call named fetch hands a request to the one object (not globalThis.fetch).
    assert CODE.count(".fetch(") == CODE.count("connection(env).fetch(request)") == 2
    assert WORKER.count('redirect: "manual"') == 1
    assert 'redirect: "follow"' not in WORKER


def test_local_wrangler_secrets_are_never_committed():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".wrangler/" in ignored
    assert ".dev.vars*" in ignored
