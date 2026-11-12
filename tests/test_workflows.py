"""Checks on the scheduled fetch, status refresh and deploy workflows (blueprint task 10)."""

import pytest
import yaml

from pipeline.refresh import refreshable
from pipeline.registry import ROOT, load_registry

WORKFLOWS = ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _fetch_step() -> dict:
    steps = _load("fetch-daily.yml")["jobs"]["fetch"]["steps"]
    return next(step for step in steps if step.get("id") == "fetch")


def _refresh_step() -> dict:
    steps = _load("refresh-statuses.yml")["jobs"]["refresh"]["steps"]
    return next(step for step in steps if step.get("id") == "refresh")


def _secrets(step: dict) -> dict:
    """The secrets a step is given, by the name it knows each one by."""
    return {name: value for name, value in step.get("env", {}).items() if "secrets." in value}


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


def test_secrets_are_used_only_in_the_fetch_step_and_the_refresh_step():
    steps = {"fetch-daily.yml": _fetch_step(), "refresh-statuses.yml": _refresh_step()}
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        uses = text.count("secrets.")
        expected = len(_secrets(steps[path.name])) if path.name in steps else 0
        assert uses == expected, f"{path.name} uses secrets outside the step that asks feeds"


def test_the_refresh_passes_every_key_a_refreshed_operator_needs_and_no_other():
    needed = set()
    for config in load_registry().values():
        if refreshable(config):
            needed |= set(config.auth.secret_names)
            if config.relay:
                # Secrets, not variables, so the address is masked in the public run logs.
                needed |= {config.relay.url_variable, config.relay.secret_name}
    given = _secrets(_refresh_step())
    assert set(given) == needed
    for name, value in given.items():
        assert value == f"${{{{ secrets.{name} }}}}"
    # The only other thing the step is told is when the last run stopped asking feeds.
    assert set(_refresh_step()["env"]) - set(given) == {"LAST_RUN_ENDED"}


def test_a_refresh_reads_statuses_and_never_publishes_map_files():
    run = _refresh_step()["run"]
    assert "pipeline.refresh --live all --map build --out statuses" in run
    assert "--previous previous" in run
    assert "--publish" not in run and "pipeline.run" not in run
    steps = _load("refresh-statuses.yml")["jobs"]["refresh"]["steps"]
    keep = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact"))
    # Its own artifact: the map files' artifact, site-data, is the daily fetch's alone.
    assert keep["with"]["name"] == "live-data" and keep["with"]["path"] == "statuses"
    assert all(s.get("with", {}).get("name") != "site-data" for s in steps)


def test_a_refresh_deploys_with_the_statuses_it_read_and_the_newest_map_files():
    deploy = _load("refresh-statuses.yml")["jobs"]["deploy"]
    assert deploy["needs"] == "refresh"
    assert deploy["uses"] == "./.github/workflows/deploy.yml"
    assert deploy["with"] == {"statuses-from-this-run": True}


def test_a_refresh_ends_before_the_next_one_starts():
    job = _load("refresh-statuses.yml")["jobs"]["refresh"]
    assert job["timeout-minutes"] < 60


def test_every_deploy_packs_the_newest_statuses_before_the_site_is_assembled():
    steps = _load("deploy.yml")["jobs"]["deploy"]["steps"]
    names = [s.get("name", "") for s in steps]
    from_run = names.index("Get the charge point statuses from this run")
    newest = names.index("Get the newest charge point statuses")
    pack = names.index("Pack the statuses read since the map files were made")
    assemble = names.index("Assemble the site (OpenFreeMap basemap)")
    assert max(from_run, newest) < pack < assemble
    assert steps[from_run]["if"] == "inputs.statuses-from-this-run"
    assert steps[from_run]["with"] == {"name": "live-data", "path": "statuses"}
    assert steps[newest]["if"] == "${{ !inputs.statuses-from-this-run }}"
    assert ".github/scripts/download-live-data.sh statuses" in steps[newest]["run"]
    assert "pipeline.live_site --map build --live statuses" in steps[pack]["run"]
    inputs = _load("deploy.yml")[True]["workflow_call"]["inputs"]
    assert inputs["statuses-from-this-run"]["default"] is False


@pytest.mark.parametrize(
    "name",
    [
        "Get the newest charge point statuses",
        "Pack the statuses read since the map files were made",
    ],
)
def test_the_map_is_deployed_even_if_the_statuses_cannot_be_had(name):
    steps = _load("deploy.yml")["jobs"]["deploy"]["steps"]
    run = next(s for s in steps if s.get("name") == name)["run"]
    # A failure is a warning, and the half-made files are removed, so the next step adds
    # empty status files (pipeline.live_site.ensure).
    assert run.lstrip().startswith("if ! ") and "::warning::" in run and "rm -rf " in run
    assert "exit" not in run


def test_the_scripts_that_download_artifacts_can_be_run():
    for script in (ROOT / ".github" / "scripts").glob("*.sh"):
        assert script.stat().st_mode & 0o111, f"{script.name} is not executable"


def test_the_site_is_packaged_with_its_well_known_folder():
    steps = _load("deploy.yml")["jobs"]["deploy"]["steps"]
    package = next(s for s in steps if s.get("uses", "").startswith("actions/upload-pages"))
    assert package["with"]["include-hidden-files"] is True


def test_the_site_is_built_from_the_newest_main():
    # A change merged while Fetch daily runs must not be replaced by the older copy.
    steps = _load("deploy.yml")["jobs"]["deploy"]["steps"]
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "main"
