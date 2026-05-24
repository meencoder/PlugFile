"""Rules-watch agent — monitor RRC rules/forms for changes and suggest features.

The Texas RRC periodically revises the plugging rule (16 TAC §3.14), the W-3 /
W-3A forms, the GAU/GW-2 groundwater process, and the online-filing guidance.
When any of those change, PlugFile's correctness engine and forms may need to
follow. This agent:

  1. fetches a curated set of RRC pages/forms (the "watch targets"),
  2. normalizes each to text and hashes it,
  3. compares against the last stored snapshot and reports what changed
     (with a unified diff), and
  4. optionally asks Claude to summarize each change in plain English and
     propose concrete PlugFile feature/engine updates to stay compliant and
     ahead.

It is designed to run on a schedule (cron / GitHub Action / Render cron) — see
``.github/workflows/rules-watch.yml`` — and to be fully testable by injecting a
fake fetcher, so the test-suite never touches the network.

Usage (CLI)::

    plugfile-rules-watch --seed                 # initialise the baseline
    plugfile-rules-watch                         # report changes since baseline
    plugfile-rules-watch --suggest --json        # + Claude feature suggestions
    plugfile-rules-watch --fail-on-change        # exit 1 if anything changed (CI)
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import difflib
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .gau_parser import _load_dotenv  # reuse the dependency-free .env loader


# ---------------------------------------------------------------------------
# Watch targets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WatchTarget:
    key: str            # stable id
    label: str          # human label
    url: str            # page or PDF to fetch
    category: str       # which PlugFile area it maps to
    kind: str = "html"  # "html" | "pdf"


# RRC restructures its site periodically — confirm/adjust these URLs. The agent
# tolerates 404s (records an error, keeps going), so a stale URL never crashes
# a run; it just surfaces as an "error" change you can fix.
WATCH_TARGETS: tuple[WatchTarget, ...] = (
    WatchTarget("plugging_overview", "RRC well plugging overview",
                "https://www.rrc.texas.gov/oil-and-gas/applications-and-permits/plugging/",
                "tac_3_14 / plug_plan", "html"),
    WatchTarget("tac_3_14", "16 TAC §3.14 (Plugging) rule text",
                "https://www.rrc.texas.gov/oil-and-gas/rules/current-oil-and-gas-rules/",
                "tac_3_14 / plug_plan", "html"),
    WatchTarget("oil_gas_forms", "RRC Oil & Gas forms library (W-3 / W-3A)",
                "https://www.rrc.texas.gov/about-us/resource-center/forms/oil-gas-forms/",
                "w3_schema / w3a_schema / pdf_export", "html"),
    WatchTarget("gau", "Groundwater Advisory Unit (GW-2 / BUQW)",
                "https://www.rrc.texas.gov/oil-and-gas/applications-and-permits/groundwater-advisory-unit/",
                "gau_parser / gau_check", "html"),
    WatchTarget("online_system", "RRC Online System / filing guidance",
                "https://www.rrc.texas.gov/resource-center/online-services/",
                "portal_format / api", "html"),
)

# category fragment -> PlugFile modules likely affected (used for no-LLM hints)
_CATEGORY_HINTS: dict[str, str] = {
    "tac_3_14": "tac_3_14.py (rule engine), plug_plan.py, aor.py",
    "plug_plan": "plug_plan.py, pdf_export.py",
    "w3_schema": "w3_schema.py, prefill.py, pdf_export.py",
    "w3a_schema": "w3a_schema.py, prefill_w3a.py, pdf_export.py",
    "pdf_export": "pdf_export.py (form overlays/coordinates)",
    "gau_parser": "gau_parser.py, gau_check.py",
    "gau_check": "gau_check.py",
    "portal_format": "portal_format.py",
    "api": "api.py (endpoints), static/ (wizards)",
}


# ---------------------------------------------------------------------------
# Fetching + normalization
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    text: str
    status: int
    error: Optional[str] = None


def _normalize(text: str) -> str:
    """Collapse whitespace so cosmetic reflow doesn't look like a change."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def _html_to_text(content: bytes) -> str:
    try:
        from lxml import html as lxml_html
    except ImportError:
        # crude fallback: strip tags
        return _normalize(re.sub(r"<[^>]+>", " ", content.decode("utf-8", "replace")))
    doc = lxml_html.fromstring(content)
    for el in doc.xpath("//script | //style | //noscript | //nav | //footer | //header"):
        el.drop_tree()
    return _normalize(doc.text_content())


def _pdf_to_text(content: bytes) -> str:
    from io import BytesIO
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(content))
    return _normalize("\n".join((p.extract_text() or "") for p in reader.pages))


def http_fetch(target: WatchTarget, *, timeout: float = 25.0) -> FetchResult:
    """Default network fetcher (real HTTP). Robust to errors."""
    import requests
    headers = {"User-Agent": "PlugFile-RulesWatch/1.0 (+https://plugfile.com)"}
    try:
        r = requests.get(target.url, headers=headers, timeout=timeout)
        status = r.status_code
        if status != 200:
            return FetchResult("", status, error=f"HTTP {status}")
        if target.kind == "pdf":
            return FetchResult(_pdf_to_text(r.content), status)
        return FetchResult(_html_to_text(r.content), status)
    except Exception as exc:  # network/parse failure — record, don't crash
        return FetchResult("", 0, error=str(exc))


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Snapshot store
# ---------------------------------------------------------------------------

class SnapshotStore:
    """Tiny JSON-file store of the last-seen text + hash per target."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict[str, Any] = {"version": 1, "targets": {}}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        self.data.setdefault("targets", {})

    def get(self, key: str) -> Optional[dict[str, Any]]:
        return self.data["targets"].get(key)

    def set(self, key: str, *, hash_: str, text: str, status: int,
            fetched_at: str) -> None:
        self.data["targets"][key] = {
            "hash": hash_, "text": text, "status": status, "fetched_at": fetched_at,
        }

    def save(self) -> None:
        self.data["saved_at"] = _now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

@dataclass
class RuleChange:
    key: str
    label: str
    url: str
    category: str
    change_type: str           # "changed" | "new" | "unchanged" | "error"
    old_hash: Optional[str]
    new_hash: Optional[str]
    diff: str = ""
    fetched_at: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class RulesReport:
    generated_at: str
    changes: list[RuleChange]
    suggestions: str = ""
    seeded: bool = False

    @property
    def changed(self) -> list[RuleChange]:
        return [c for c in self.changes if c.change_type in ("changed", "new")]

    @property
    def errors(self) -> list[RuleChange]:
        return [c for c in self.changes if c.change_type == "error"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "seeded": self.seeded,
            "summary": {
                "total": len(self.changes),
                "changed": len(self.changed),
                "errors": len(self.errors),
            },
            "changes": [c.to_dict() for c in self.changes],
            "suggestions": self.suggestions,
        }


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unified_diff(old: str, new: str, *, max_lines: int = 80) -> str:
    # diff on sentence-ish chunks so a normalized one-line blob is still useful
    old_lines = re.split(r"(?<=[.;:])\s+", old)
    new_lines = re.split(r"(?<=[.;:])\s+", new)
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=1))
    if len(diff) > max_lines:
        diff = diff[:max_lines] + [f"... (+{len(diff) - max_lines} more diff lines)"]
    return "\n".join(diff)


def check_for_changes(
    targets: tuple[WatchTarget, ...],
    store: SnapshotStore,
    *,
    fetcher: Callable[[WatchTarget], FetchResult] = http_fetch,
    seed: bool = False,
) -> list[RuleChange]:
    """Fetch each target, compare to the store, and return the changes.

    ``seed=True`` records the current state as the baseline and reports every
    target as ``unchanged`` (so a first run doesn't flag everything as new).
    The store is updated in memory; call ``store.save()`` to persist.
    """
    now = _now_iso()
    changes: list[RuleChange] = []
    for t in targets:
        res = fetcher(t)
        if res.error or res.status != 200:
            changes.append(RuleChange(t.key, t.label, t.url, t.category, "error",
                                      old_hash=(store.get(t.key) or {}).get("hash"),
                                      new_hash=None, fetched_at=now, error=res.error or f"HTTP {res.status}"))
            continue
        # Normalize here too, so whitespace-insensitivity is a property of the
        # agent regardless of the fetcher (the HTTP fetcher already normalizes;
        # re-normalizing is idempotent).
        text = _normalize(res.text)
        new_hash = _hash(text)
        prev = store.get(t.key)
        if prev is None:
            ctype = "unchanged" if seed else "new"
            diff = "" if seed else "(no prior snapshot — first time this target was seen)"
            changes.append(RuleChange(t.key, t.label, t.url, t.category, ctype,
                                      old_hash=None, new_hash=new_hash, diff=diff, fetched_at=now))
        elif prev.get("hash") != new_hash:
            changes.append(RuleChange(t.key, t.label, t.url, t.category, "changed",
                                      old_hash=prev.get("hash"), new_hash=new_hash,
                                      diff=_unified_diff(prev.get("text", ""), text),
                                      fetched_at=now))
        else:
            changes.append(RuleChange(t.key, t.label, t.url, t.category, "unchanged",
                                      old_hash=prev.get("hash"), new_hash=new_hash, fetched_at=now))
        store.set(t.key, hash_=new_hash, text=text, status=res.status, fetched_at=now)
    return changes


# ---------------------------------------------------------------------------
# Feature suggestions
# ---------------------------------------------------------------------------

def _heuristic_suggestions(changes: list[RuleChange]) -> str:
    changed = [c for c in changes if c.change_type in ("changed", "new")]
    if not changed:
        return "No rule/form changes detected. No action needed."
    lines = ["Changes detected — review impact on these PlugFile modules:"]
    for c in changed:
        hint = "; ".join(
            mod for frag, mod in _CATEGORY_HINTS.items() if frag in c.category
        ) or "review relevant modules"
        lines.append(f"  • [{c.change_type}] {c.label} → {hint}")
        lines.append(f"      {c.url}")
    lines.append("Run with --suggest (and ANTHROPIC_API_KEY set) for AI feature proposals.")
    return "\n".join(lines)


def suggest_features(changes: list[RuleChange], *, use_llm: bool = False) -> str:
    """Summarize the changes and propose PlugFile features.

    Without ``use_llm`` (or without an API key) returns a deterministic,
    module-mapped heuristic. With both, asks Claude for prioritized proposals.
    """
    changed = [c for c in changes if c.change_type in ("changed", "new")]
    if not changed:
        return _heuristic_suggestions(changes)
    if not use_llm:
        return _heuristic_suggestions(changes)

    _load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return _heuristic_suggestions(changes) + \
            "\n(ANTHROPIC_API_KEY not set — showing heuristic suggestions only.)"
    try:
        import anthropic
    except ImportError:
        return _heuristic_suggestions(changes) + "\n(anthropic not installed.)"

    client = anthropic.Anthropic()
    model = _pick_model(client)
    context = (
        "PlugFile is software that prepares Texas RRC well-plugging filings "
        "(Forms W-3 and W-3A). Its modules include: a §3.14 rule engine "
        "(tac_3_14.py, plug_plan.py), GAU/BUQW parsing + an H-15 acceptability "
        "check (gau_parser.py, gau_check.py), area-of-review (aor.py), "
        "required-attachments and portal-format validators, district routing, "
        "PDF generation (pdf_export.py), and two PWA wizards."
    )
    changes_blob = "\n\n".join(
        f"### {c.label} ({c.change_type}) — {c.url}\nMaps to: {c.category}\n"
        f"Diff (sentence-level):\n{c.diff[:2500]}"
        for c in changed
    )
    prompt = (
        f"{context}\n\nThe following RRC rule/form pages changed:\n\n{changes_blob}\n\n"
        "For EACH change: (1) summarize in plain English what appears to have "
        "changed, and (2) propose concrete, prioritized PlugFile product/engine "
        "updates or NEW features to stay compliant and ahead of competitors. "
        "Name the likely module(s) to touch. Be specific and concise. If a diff "
        "is inconclusive, say so and recommend a manual review step."
    )
    try:
        resp = client.messages.create(
            model=model, max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    except Exception as exc:
        return _heuristic_suggestions(changes) + f"\n(LLM suggestion failed: {exc})"


def _pick_model(client) -> str:  # type: ignore[valid-type]
    override = os.environ.get("PLUGFILE_LLM_MODEL", "").strip()
    if override:
        return override
    try:
        ids = [m.id for m in client.models.list().data]
        for pref in ("sonnet", "opus", "haiku", "claude"):
            found = next((i for i in ids if pref in i.lower()), None)
            if found:
                return found
    except Exception:
        pass
    return "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_watch(
    *,
    store_path: str | Path,
    targets: tuple[WatchTarget, ...] = WATCH_TARGETS,
    fetcher: Callable[[WatchTarget], FetchResult] = http_fetch,
    seed: bool = False,
    use_llm: bool = False,
) -> RulesReport:
    """End-to-end: load store → check → suggest → persist → return report."""
    store = SnapshotStore(store_path)
    changes = check_for_changes(targets, store, fetcher=fetcher, seed=seed)
    suggestions = "" if seed else suggest_features(changes, use_llm=use_llm)
    store.save()
    report = RulesReport(generated_at=_now_iso(), changes=changes,
                         suggestions=suggestions, seeded=seed)
    return report


def default_store_path() -> str:
    return os.environ.get("PLUGFILE_RULES_STORE", "rules_snapshots.json")


def latest_report(store_path: str | Path | None = None) -> dict[str, Any]:
    """Read-only summary of the last run, for the API/status surface."""
    store = SnapshotStore(store_path or default_store_path())
    if not store.data.get("targets"):
        return {"available": False, "message": "No rules snapshot yet — run plugfile-rules-watch --seed."}
    return {
        "available": True,
        "saved_at": store.data.get("saved_at"),
        "targets": {
            k: {"fetched_at": v.get("fetched_at"), "status": v.get("status"),
                "hash": (v.get("hash") or "")[:12]}
            for k, v in store.data["targets"].items()
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main() -> int:
    ap = argparse.ArgumentParser(prog="plugfile-rules-watch",
        description="Monitor RRC rules/forms for changes and suggest PlugFile features.")
    ap.add_argument("--store", default=default_store_path(), help="Snapshot JSON path.")
    ap.add_argument("--seed", action="store_true", help="Record baseline; don't flag changes.")
    ap.add_argument("--suggest", action="store_true", help="Use Claude for feature suggestions.")
    ap.add_argument("--json", action="store_true", help="Emit JSON.")
    ap.add_argument("--report", help="Also write the JSON report to this path.")
    ap.add_argument("--fail-on-change", action="store_true", help="Exit 1 if anything changed (for CI).")
    args = ap.parse_args()

    report = run_watch(store_path=args.store, seed=args.seed, use_llm=args.suggest)
    out = report.to_dict()
    if args.report:
        Path(args.report).write_text(json.dumps(out, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        s = out["summary"]
        print(f"Rules-watch {report.generated_at} — {s['changed']} changed, "
              f"{s['errors']} error(s), {s['total']} target(s)"
              + (" [seed]" if args.seed else ""))
        for c in report.changes:
            mark = {"changed": "CHANGED", "new": "NEW", "error": "ERROR ", "unchanged": "ok    "}[c.change_type]
            print(f"  {mark}  {c.label}" + (f"  ({c.error})" if c.error else ""))
        if not args.seed and report.suggestions:
            print("\n--- Suggestions ---\n" + report.suggestions)

    if args.fail_on_change and report.changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
