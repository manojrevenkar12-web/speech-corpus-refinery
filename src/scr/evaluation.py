"""How well the refinery did on a world whose truth is known. Only this module reads
truth.json; nothing that decides reads it.

Measured: the decision for every audio file (keep or not, and whether the reason is the right
kind), rights compliance from the server's own request log (blocked domains, robots.txt, TDM
reservations), duplicates, the protected set, synthetic speech, and transcript quality of kept
segments against the true text."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import align, db

FAMILY = {
    "robots": "rights",
    "tdm": "rights",
    "blocked_domain": "rights",
    "takedown": "rights",
    "fetch": "fetch",
    "corrupt": "fetch",
    "licence": "licence",
    "synthetic": "synthetic",
    "synthetic_suspected": "synthetic",
    "protected": "protected",
    "duplicate": "duplicate",
    "not_speech": "not_speech",
    "too_short": "not_speech",
    "bandwidth": "quality",
    "music": "quality",
    "noise": "quality",
    "clipping": "quality",
    "language": "quality",
    "misaligned": "quality",
    "no_text": "quality",
}


def _got(url: str, items: dict[str, dict[str, Any]], urls: dict[str, dict[str, Any]]) -> str:
    it = items.get(url)
    if it is not None:
        if it["state"] == "kept":
            return "kept"
        return f"{it['state']}:{it['reason']}"
    u = urls.get(url)
    if u is None:
        return "not_fetched:never discovered"
    return f"not_fetched:{u['reason'] or u['state']}"


def evaluate(world: Path, log: list[dict[str, Any]], url: str | None = None) -> dict[str, Any]:
    truth = json.loads((world / "truth.json").read_text())
    with db.tx(url) as c:
        items = {
            r["url"]: r for r in c.execute("SELECT u.url, i.id, i.state, i.reason, i.detail FROM items i JOIN urls u ON u.id = i.url_id")
        }
        urls = {r["url"]: r for r in c.execute("SELECT url, state, reason FROM urls")}
        segs: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in c.execute("SELECT item_id, start_s, end_s, text, cer, state FROM segments ORDER BY item_id, idx"):
            segs[r["item_id"]].append(r)

    rows: list[dict[str, Any]] = []
    by_expected: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "decision_ok": 0, "reason_ok": 0})
    for t in truth:
        got = _got(t["url"], items, urls)
        exp_keep = t["expected"] == "keep"
        dec_ok = exp_keep == (got == "kept")
        exp_reason = t["expected"].split(":", 1)[1] if ":" in t["expected"] else "keep"
        got_reason = got.split(":", 1)[1] if ":" in got else "keep"
        if got.startswith("not_fetched"):
            reason_ok = t["blocked_by"] != ""
        else:
            reason_ok = (
                got == "kept"
                if exp_keep
                else FAMILY.get(got_reason, got_reason)
                in {FAMILY.get(exp_reason, exp_reason), *(FAMILY.get(d, d) for d in t["defects"])}
                | ({"duplicate"} if t["duplicate_of"] else set())
            )
        b = by_expected[t["expected"]]
        b["n"] += 1
        b["decision_ok"] += dec_ok
        b["reason_ok"] += bool(reason_ok)
        rows.append({"url": t["url"], "expected": t["expected"], "got": got, "decision_ok": dec_ok, "reason_ok": bool(reason_ok)})

    # rights compliance, from what the server saw
    def paths(kind: str) -> set[tuple[str, str]]:
        return {(urlsplit(t["url"]).netloc, urlsplit(t["url"]).path) for t in truth if t["blocked_by"] == kind}

    seen = Counter((e["host"], e["path"]) for e in log)
    robots_violations = sum(seen[p] for p in paths("robots"))
    tdm_file_paths = {p for p in paths("tdm") if "/studio/" in p[1]}
    compliance = {
        "requests": len(log),
        "requests_to_blocked_domains": sum(1 for e in log if e["host"] == "pirate.example"),
        "requests_disallowed_by_robots": robots_violations,
        "requests_to_tdm_reserved_paths_in_tdmrep_json": sum(seen[p] for p in tdm_file_paths),
        "reserved_files_stored": sum(1 for t in truth if t["blocked_by"] == "tdm" and t["url"] in items),
        "user_agents": sorted({e["ua"] for e in log}),
    }

    # synthetic speech
    declared = [r for r, t in zip(rows, truth, strict=True) if t["synthetic"] and t.get("declared")]
    undeclared = [r for r, t in zip(rows, truth, strict=True) if t["synthetic"] and not t.get("declared") and not t["blocked_by"]]
    real_held = [r for r, t in zip(rows, truth, strict=True) if not t["synthetic"] and r["got"].startswith("held:")]
    synthetic = {
        "declared": len(declared),
        "declared_rejected": sum(1 for r in declared if r["got"] == "rejected:synthetic"),
        "undeclared": len(undeclared),
        "undeclared_held_for_review": sum(1 for r in undeclared if r["got"].startswith("held:")),
        "undeclared_rejected_for_another_reason": sum(1 for r in undeclared if r["got"].startswith("rejected:")),
        "undeclared_kept": sum(1 for r in undeclared if r["got"] == "kept"),
        "real_speech_held": len(real_held),
    }

    # transcripts of kept segments against the true text of each clip
    label: dict[str, list[float]] = {"published": [], "asr": []}
    covered = []
    for t in truth:
        it = items.get(t["url"])
        if not it or it["state"] != "kept" or not t["clips"]:
            continue
        kept = [s for s in segs[it["id"]] if s["state"] == "kept"]
        for clip in t["clips"]:
            inside = [s for s in kept if clip["start"] <= (s["start_s"] + s["end_s"]) / 2 <= clip["end"]]
            if not inside:
                continue
            text = " ".join(s["text"] for s in inside)
            kind = "published" if all(s["cer"] is not None for s in inside) else "asr"
            label[kind].append(align.cer(clip["text"], text))
            dur = clip["end"] - clip["start"]
            covered.append(min(1.0, sum(min(s["end_s"], clip["end"]) - max(s["start_s"], clip["start"]) for s in inside) / dur))
    transcripts: dict[str, Any] = {
        k: {"clips": len(v), "mean_cer": round(sum(v) / len(v), 4) if v else None, "max_cer": round(max(v), 4) if v else None}
        for k, v in label.items()
    }
    transcripts["coverage_of_true_speech"] = round(sum(covered) / len(covered), 3) if covered else None

    n = len(rows)
    return {
        "files": n,
        "decisions_correct": sum(r["decision_ok"] for r in rows),
        "reasons_correct": sum(r["reason_ok"] for r in rows),
        "by_expected": {k: dict(v) for k, v in sorted(by_expected.items())},
        "kept": {"expected": sum(1 for t in truth if t["expected"] == "keep"), "got": sum(1 for r in rows if r["got"] == "kept")},
        "compliance": compliance,
        "synthetic": synthetic,
        "transcripts": transcripts,
        "wrong": [r for r in rows if not r["decision_ok"]],
        "reason_mismatches": [r for r in rows if r["decision_ok"] and not r["reason_ok"]],
    }


def markdown(ev: dict[str, Any], title: str = "Evaluation on the test world") -> str:
    c, s, tr = ev["compliance"], ev["synthetic"], ev["transcripts"]
    out = [
        f"# {title}",
        "",
        f"{ev['decisions_correct']} of {ev['files']} files got the right decision (keep or not); {ev['reasons_correct']} also got the right kind of reason. "
        f"{ev['kept']['got']} kept, {ev['kept']['expected']} should be.",
        "",
        "| Expected | Files | Right decision | Right reason |",
        "|---|---:|---:|---:|",
    ]
    out += [f"| {k} | {v['n']} | {v['decision_ok']} | {v['reason_ok']} |" for k, v in ev["by_expected"].items()]
    out += [
        "",
        "## Rights, from the server's own request log",
        "",
        f"- Requests: {c['requests']}; user agents seen: {', '.join(f'`{u}`' for u in c['user_agents'])}",
        f"- Requests to a blocked domain: {c['requests_to_blocked_domains']}",
        f"- Requests to paths robots.txt disallows: {c['requests_disallowed_by_robots']}",
        f"- Requests to paths reserved in tdmrep.json: {c['requests_to_tdm_reserved_paths_in_tdmrep_json']}",
        f"- Files reserved by a TDM header or meta tag that were stored: {c['reserved_files_stored']}",
        "",
        "## Synthetic speech",
        "",
        f"- Declared (IPTC trainedAlgorithmicMedia in schema.org): {s['declared_rejected']} of {s['declared']} rejected",
        f"- Undeclared: {s['undeclared_held_for_review']} of {s['undeclared']} held for review, {s.get('undeclared_rejected_for_another_reason', 0)} rejected for another reason, {s['undeclared_kept']} kept",
        f"- Real speech held by mistake: {s['real_speech_held']}",
        "",
        "## Transcripts of kept segments, against the true text",
        "",
        "| Text source | Clips | Mean CER | Worst CER |",
        "|---|---:|---:|---:|",
    ]
    out += [f"| {k} | {v['clips']} | {v['mean_cer']} | {v['max_cer']} |" for k, v in tr.items() if isinstance(v, dict)]
    out += [
        "",
        f"Kept segments cover {tr['coverage_of_true_speech']:.0%} of the true speech in kept files."
        if tr["coverage_of_true_speech"]
        else "",
        "",
    ]
    if ev["wrong"]:
        out += ["## Wrong decisions", "", "| File | Expected | Got |", "|---|---|---|"]
        out += [f"| {r['url']} | {r['expected']} | {r['got']} |" for r in ev["wrong"]]
        out.append("")
    if ev["reason_mismatches"]:
        out += ["## Right decision, other reason", "", "| File | Expected | Got |", "|---|---|---|"]
        out += [f"| {r['url']} | {r['expected']} | {r['got']} |" for r in ev["reason_mismatches"]]
        out.append("")
    return "\n".join(out)
