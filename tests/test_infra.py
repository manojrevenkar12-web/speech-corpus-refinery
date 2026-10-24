"""The GCP deployment's invariants, read from the Terraform itself (CI also runs terraform validate)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scr import config

hcl2 = pytest.importorskip("hcl2")
TF = Path(__file__).resolve().parents[1] / "infra" / "terraform"


def _clean(v: Any) -> Any:
    if isinstance(v, dict):
        return {_clean(k): _clean(x) for k, x in v.items() if k not in ("__is_block__", "__comments__")}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] == '"':
        return v[1:-1]
    return v


def _load() -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for f in sorted(TF.glob("*.tf")):
        with f.open() as fh:
            doc = _clean(hcl2.load(fh))
        for block in doc.get("resource", []):
            for rtype, named in block.items():
                for name, body in named.items():
                    out.setdefault(rtype, {})[name] = body
    return out


R = _load()
TEXT = "\n".join(p.read_text() for p in TF.glob("*.tf"))


def _first(v: Any) -> Any:
    return v[0] if isinstance(v, list) and v else v


def _containers(body: dict[str, Any]) -> list[dict[str, Any]]:
    t = _first(body["template"])
    t = _first(t.get("template", [t]))  # jobs nest a task template
    return t["containers"] if isinstance(t["containers"], list) else [t["containers"]]


def _task(body: dict[str, Any]) -> dict[str, Any]:
    t = _first(body["template"])
    return _first(t.get("template", [t]))


def test_no_principal_gets_a_project_wide_role():
    assert "google_project_iam_member" not in R and "google_project_iam_binding" not in R and "google_project_iam_policy" not in R
    for broad in ("roles/owner", "roles/editor", "roles/storage.admin", "roles/storage.objectAdmin", "allUsers", "allAuthenticatedUsers"):
        assert broad not in TEXT, broad


def test_buckets_are_private_and_takedowns_really_delete():
    for name, b in R["google_storage_bucket"].items():
        assert b["public_access_prevention"] == "enforced" and b["uniform_bucket_level_access"] is True, name
    assert _first(R["google_storage_bucket"]["raw"]["soft_delete_policy"])["retention_duration_seconds"] == 0
    assert _first(R["google_storage_bucket"]["releases"]["versioning"])["enabled"] is True


def test_only_the_takedown_path_can_delete_audio_and_the_crawler_cannot_overwrite():
    deleters = [m for m in R["google_storage_bucket_iam_member"].values() if "takedown_deleter" in str(m["role"])]
    assert len(deleters) == 1 and "api" in deleters[0]["member"]
    perms = R["google_project_iam_custom_role"]["takedown_deleter"]["permissions"]
    assert sorted(perms) == ["storage.objects.delete", "storage.objects.get"]
    crawler_roles = {
        m["role"] for m in R["google_storage_bucket_iam_member"].values() if '"crawler"' in m["member"] or "crawler" in m["member"]
    }
    assert crawler_roles <= {"roles/storage.objectCreator", "roles/storage.objectViewer"}


def test_database_is_private_encrypted_backed_up_and_protected():
    pg = R["google_sql_database_instance"]["pg"]
    s = _first(pg["settings"])
    ip = _first(s["ip_configuration"])
    assert pg["deletion_protection"] is True and ip["ipv4_enabled"] is False and ip["ssl_mode"] == "ENCRYPTED_ONLY"
    bk = _first(s["backup_configuration"])
    assert bk["enabled"] is True and bk["point_in_time_recovery_enabled"] is True


def test_every_workload_runs_as_its_own_account_with_secrets_from_secret_manager():
    workloads = {**R["google_cloud_run_v2_job"], **R["google_cloud_run_v2_service"]}
    assert set(workloads) == {"crawl", "work", "release", "setup", "api"}
    for name, body in workloads.items():
        assert "google_service_account.sa" in _task(body)["service_account"], name
        for c in _containers(body):
            assert c["image"] == "${var.image}", name
            envs = c.get("env", [])
            for e in envs if isinstance(envs, list) else [envs]:
                assert "postgresql://" not in str(e.get("value", "")), name
                if e["name"] in ("SCR_DATABASE_URL", "SCR_API_KEYS"):
                    assert "value_source" in e, (name, e["name"])
    assert re.search(r'can\(regex\("@sha256:\[0-9a-f\]\{64\}\$", var\.image\)\)', TEXT), "image must be pinned by digest"


def test_the_crawler_leaves_from_one_published_static_address():
    crawl = _task(R["google_cloud_run_v2_job"]["crawl"])
    assert _first(crawl["vpc_access"])["egress"] == "ALL_TRAFFIC"
    nat = R["google_compute_router_nat"]["egress"]
    assert nat["nat_ip_allocate_option"] == "MANUAL_ONLY" and "crawler_egress" in str(nat["nat_ips"])
    assert R["google_compute_address"]["crawler_egress"]["address_type"] == "EXTERNAL"


def test_the_scheduler_can_start_only_the_scheduled_jobs():
    inv = R["google_cloud_run_v2_job_iam_member"]["invoke"]
    assert inv["role"] == "roles/run.invoker" and set(re.findall(r"(crawl|work) =", json.dumps(inv["for_each"]).replace('\\"', ""))) <= {
        "crawl",
        "work",
    }
    assert "release" not in json.dumps(inv["for_each"]) and "setup" not in json.dumps(inv["for_each"])


def test_worker_size_matches_what_the_cost_report_assumes():
    variables: dict[str, Any] = {}
    with (TF / "variables.tf").open() as fh:
        for v in _clean(hcl2.load(fh))["variable"]:
            variables.update(v)
    job = config.pricing()["cloud_run_job"]
    assert float(variables["worker_cpu"]["default"]) == float(job["vcpu"])
    assert variables["worker_memory"]["default"] == f"{int(job['gib'])}Gi"
    assert variables["worker_parallelism"]["default"] * 2 < 100  # under max_connections, each task holding a pool
