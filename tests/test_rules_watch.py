"""Tests for the RRC rules-watch agent (rules_watch.py).

A fake fetcher returns canned content so the suite never touches the network.
"""

from __future__ import annotations

import json

import pytest

from plugfile.rules_watch import (
    FetchResult,
    RulesReport,
    SnapshotStore,
    WatchTarget,
    check_for_changes,
    latest_report,
    run_watch,
    suggest_features,
)

T1 = WatchTarget("a", "Rule A", "https://rrc/a", "tac_3_14 / plug_plan", "html")
T2 = WatchTarget("b", "Form B", "https://rrc/b", "w3a_schema / pdf_export", "html")
TARGETS = (T1, T2)


def make_fetcher(content: dict[str, str], errors: dict[str, str] | None = None):
    errors = errors or {}
    def f(t: WatchTarget) -> FetchResult:
        if t.key in errors:
            return FetchResult("", errors[t.key].startswith("HTTP") and 404 or 0, error=errors[t.key])
        return FetchResult(content.get(t.key, ""), 200)
    return f


# ── seeding ──────────────────────────────────────────────────────────────────

def test_seed_records_baseline_without_flagging(tmp_path):
    store = SnapshotStore(tmp_path / "s.json")
    changes = check_for_changes(TARGETS, store, fetcher=make_fetcher({"a": "AAA", "b": "BBB"}), seed=True)
    assert all(c.change_type == "unchanged" for c in changes)
    assert store.get("a")["hash"]


def test_first_run_without_seed_marks_new(tmp_path):
    store = SnapshotStore(tmp_path / "s.json")
    changes = check_for_changes(TARGETS, store, fetcher=make_fetcher({"a": "AAA", "b": "BBB"}))
    assert {c.change_type for c in changes} == {"new"}


# ── change detection ───────────────────────────────────────────────────────────

def test_unchanged_when_content_same(tmp_path):
    p = tmp_path / "s.json"
    f1 = make_fetcher({"a": "hello world", "b": "form text"})
    s = SnapshotStore(p)
    check_for_changes(TARGETS, s, fetcher=f1, seed=True)
    s.save()
    # re-open store, same content
    changes = check_for_changes(TARGETS, SnapshotStore(p), fetcher=f1)
    assert all(c.change_type == "unchanged" for c in changes)


def test_detects_change_with_diff(tmp_path):
    p = tmp_path / "s.json"
    s = SnapshotStore(p)
    check_for_changes(TARGETS, s, fetcher=make_fetcher({"a": "The plug must be 50 ft. End.", "b": "B"}), seed=True)
    s.save()
    s2 = SnapshotStore(p)
    changes = check_for_changes(TARGETS, s2,
        fetcher=make_fetcher({"a": "The plug must be 100 ft. End.", "b": "B"}))
    a = next(c for c in changes if c.key == "a")
    b = next(c for c in changes if c.key == "b")
    assert a.change_type == "changed"
    assert a.old_hash != a.new_hash
    assert "100 ft" in a.diff or "50 ft" in a.diff
    assert b.change_type == "unchanged"


def test_whitespace_only_change_is_not_flagged(tmp_path):
    p = tmp_path / "s.json"
    s = SnapshotStore(p)
    check_for_changes(TARGETS, s, fetcher=make_fetcher({"a": "one two three", "b": "x"}), seed=True)
    s.save()
    changes = check_for_changes(TARGETS, SnapshotStore(p),
        fetcher=make_fetcher({"a": "one   two\n\nthree", "b": "x"}))  # reflowed only
    assert next(c for c in changes if c.key == "a").change_type == "unchanged"


def test_fetch_error_recorded_not_crash(tmp_path):
    store = SnapshotStore(tmp_path / "s.json")
    changes = check_for_changes(TARGETS, store,
        fetcher=make_fetcher({"b": "ok"}, errors={"a": "HTTP 404"}))
    a = next(c for c in changes if c.key == "a")
    assert a.change_type == "error"
    assert a.error


# ── suggestions (no LLM) ────────────────────────────────────────────────────────

def test_no_changes_suggestion():
    changes = [c for c in check_for_changes(
        TARGETS, SnapshotStore("x"), fetcher=make_fetcher({"a": "A", "b": "B"}), seed=True)]
    assert "No rule/form changes" in suggest_features(changes)


def test_heuristic_maps_to_modules(tmp_path):
    p = tmp_path / "s.json"
    s = SnapshotStore(p)
    check_for_changes(TARGETS, s, fetcher=make_fetcher({"a": "v1", "b": "v1"}), seed=True)
    s.save()
    changes = check_for_changes(TARGETS, SnapshotStore(p),
        fetcher=make_fetcher({"a": "v2-changed", "b": "v1"}))
    sug = suggest_features(changes, use_llm=False)
    assert "Rule A" in sug
    assert "tac_3_14.py" in sug   # mapped from the category


# ── orchestration + report shape ────────────────────────────────────────────────

def test_run_watch_seed_then_change(tmp_path):
    p = tmp_path / "s.json"
    run_watch(store_path=p, targets=TARGETS, fetcher=make_fetcher({"a": "A1", "b": "B1"}), seed=True)
    rep = run_watch(store_path=p, targets=TARGETS, fetcher=make_fetcher({"a": "A2", "b": "B1"}))
    assert isinstance(rep, RulesReport)
    assert len(rep.changed) == 1
    assert rep.changed[0].key == "a"


def test_report_to_dict_json_serializable(tmp_path):
    p = tmp_path / "s.json"
    rep = run_watch(store_path=p, targets=TARGETS, fetcher=make_fetcher({"a": "A", "b": "B"}), seed=True)
    d = rep.to_dict()
    json.dumps(d)
    assert d["seeded"] is True
    assert d["summary"]["total"] == 2
    assert len(d["changes"]) == 2


def test_store_persists_to_disk(tmp_path):
    p = tmp_path / "s.json"
    run_watch(store_path=p, targets=TARGETS, fetcher=make_fetcher({"a": "A", "b": "B"}), seed=True)
    assert p.exists()
    data = json.loads(p.read_text())
    assert "a" in data["targets"] and "b" in data["targets"]


def test_latest_report_reads_store(tmp_path):
    p = tmp_path / "s.json"
    assert latest_report(p)["available"] is False
    run_watch(store_path=p, targets=TARGETS, fetcher=make_fetcher({"a": "A", "b": "B"}), seed=True)
    lr = latest_report(p)
    assert lr["available"] is True
    assert "a" in lr["targets"]


def test_latest_report_surfaces_last_changes(tmp_path):
    p = tmp_path / "s.json"
    run_watch(store_path=p, targets=TARGETS, fetcher=make_fetcher({"a": "A1", "b": "B1"}), seed=True)
    run_watch(store_path=p, targets=TARGETS, fetcher=make_fetcher({"a": "A2", "b": "B1"}))
    lr = latest_report(p)
    assert lr["last_report"]["summary"]["changed"] == 1
    assert any(c["key"] == "a" and c["change_type"] == "changed"
               for c in lr["last_report"]["changes"])
