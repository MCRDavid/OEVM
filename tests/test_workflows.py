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
        for name in config.auth.secret_names if config.enabled else ():
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
            needed |= set(config.auth.secret_names)
            if config.relay:
                needed |= {config.relay.url_variable, config.relay.secret_name}
    assert set(_fetch_step().get("env", {})) <= needed


def test_two_daily_fetches_never_run_at_once():
    concurrency = _load("fetch-daily.yml")["concurrency"]
    assert concurrency["cancel-in-progress"] is False
    assert "--live all" in _fetch_step()["run"]


# A one-off the owner asked for on 6 November 2026, to be removed once read.
MONTA_NOTES = "read-monta-notes-once.yml"


def _monta_notes_steps() -> list[dict]:
    return _load(MONTA_NOTES)["jobs"]["notes"]["steps"]


def test_secrets_are_used_only_in_the_fetch_step():
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        uses = text.count("secrets.")
        if path.name == "fetch-daily.yml":
            env = _fetch_step().get("env", {})
        elif path.name == MONTA_NOTES:
            env = next(s for s in _monta_notes_steps() if "pipeline.run" in s.get("run", ""))["env"]
        else:
            env = {}
        secrets = [value for value in env.values() if "secrets." in value]
        assert uses == len(secrets), f"{path.name} uses secrets outside the fetch step"


def test_the_one_off_monta_read_uses_only_its_keys_and_never_overlaps_a_fetch():
    workflow = _load(MONTA_NOTES)
    assert workflow["concurrency"] == _load("fetch-daily.yml")["concurrency"]
    assert workflow["jobs"]["notes"]["if"] == "github.ref == 'refs/heads/main'"
    fetch = next(s for s in _monta_notes_steps() if "pipeline.run" in s.get("run", ""))
    assert "--live monta " in fetch["run"]
    names = set(load_registry()["monta"].auth.secret_names)
    assert fetch["env"] == {name: f"${{{{ secrets.{name} }}}}" for name in names}
    # Only the encrypted files leave the runner.
    upload = next(s for s in _monta_notes_steps() if "upload-artifact" in s.get("uses", ""))
    assert upload["with"]["path"] == "${{ runner.temp }}/out"
    encrypt = next(s for s in _monta_notes_steps() if "openssl enc" in s.get("run", ""))
    assert "notes.json.enc" in encrypt["run"] and 'shred -u "$RUNNER_TEMP/secret"' in encrypt["run"]


def test_the_site_is_packaged_with_its_well_known_folder():
    steps = _load("deploy.yml")["jobs"]["deploy"]["steps"]
    package = next(s for s in steps if s.get("uses", "").startswith("actions/upload-pages"))
    assert package["with"]["include-hidden-files"] is True


def test_the_site_is_built_from_the_newest_main():
    # A change merged while Fetch daily runs must not be replaced by the older copy.
    steps = _load("deploy.yml")["jobs"]["deploy"]["steps"]
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "main"
