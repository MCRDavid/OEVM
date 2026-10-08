"""Checks on the scheduled fetch and deploy workflows (blueprint task 10)."""

import yaml

from pipeline.registry import ROOT, load_registry

WORKFLOWS = ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _fetch_step() -> dict:
    steps = _load("fetch-daily.yml")["jobs"]["fetch"]["steps"]
    return next(step for step in steps if step.get("id") == "fetch")


def test_the_daily_fetch_passes_every_key_an_enabled_operator_needs():
    env = _fetch_step().get("env", {})
    for config in load_registry().values():
        name = config.auth.secret_name
        if config.enabled and name:
            assert env.get(name) == f"${{{{ secrets.{name} }}}}", f"{config.id} needs {name}"


def test_the_daily_fetch_passes_every_relay_setting():
    env = _fetch_step().get("env", {})
    for config in load_registry().values():
        if config.enabled and config.relay:
            relay = config.relay
            # A secret, not a variable, so the address is masked in the public run logs.
            assert env.get(relay.url_variable) == f"${{{{ secrets.{relay.url_variable} }}}}"
            assert env.get(relay.secret_name) == f"${{{{ secrets.{relay.secret_name} }}}}"


def test_the_daily_fetch_passes_no_other_secrets():
    needed = set()
    for config in load_registry().values():
        if config.enabled:
            needed.add(config.auth.secret_name)
            if config.relay:
                needed |= {config.relay.url_variable, config.relay.secret_name}
    assert set(_fetch_step().get("env", {})) <= needed


def test_two_daily_fetches_never_run_at_once():
    concurrency = _load("fetch-daily.yml")["concurrency"]
    assert concurrency["cancel-in-progress"] is False
    assert "--live all" in _fetch_step()["run"]


def test_secrets_are_used_only_in_the_fetch_step():
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        uses = text.count("secrets.")
        env = _fetch_step().get("env", {})
        secrets = [value for value in env.values() if "secrets." in value]
        expected = len(secrets) if path.name == "fetch-daily.yml" else 0
        assert uses == expected, f"{path.name} uses secrets outside the fetch step"


def test_the_site_is_packaged_with_its_well_known_folder():
    steps = _load("deploy.yml")["jobs"]["deploy"]["steps"]
    package = next(s for s in steps if s.get("uses", "").startswith("actions/upload-pages"))
    assert package["with"]["include-hidden-files"] is True
