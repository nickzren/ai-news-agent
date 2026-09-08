"""Handler-entry invalidation of generated preflight and candidate artifacts."""

import argparse
import builtins
import json
import logging
from pathlib import Path

import graph
import main
import pytest


@pytest.fixture
def artifacts(tmp_path):
    args = argparse.Namespace(
        issue_status_file=tmp_path / "custom-issue.json",
        status_file=tmp_path / "custom-status.json",
        candidates_file=tmp_path / "custom-candidates.json",
    )
    for path in vars(args).values():
        path.write_text('{"stale": true}', encoding="utf-8")
    return args


def test_issue_check_removes_old_status_before_unexpected_failure(artifacts, monkeypatch):
    def fail_check():
        assert not artifacts.issue_status_file.exists()
        raise ValueError("unexpected response")

    monkeypatch.setattr(main, "check_issue_status", fail_check)

    with pytest.raises(ValueError, match="unexpected response"):
        main._run_check_issue(artifacts, logging.getLogger(__name__))

    assert not artifacts.issue_status_file.exists()
    assert json.loads(artifacts.status_file.read_text()) == {"stale": True}
    assert json.loads(artifacts.candidates_file.read_text()) == {"stale": True}


@pytest.mark.parametrize("old_file_exists", [False, True])
def test_issue_check_writes_fresh_success(artifacts, monkeypatch, old_file_exists):
    if not old_file_exists:
        artifacts.issue_status_file.unlink()

    def check():
        assert not artifacts.issue_status_file.exists()
        return {"exists": False, "issue_number": None, "title": "AI Headlines - Sep 8"}

    monkeypatch.setattr(main, "check_issue_status", check)
    main._run_check_issue(artifacts, logging.getLogger(__name__))

    assert json.loads(artifacts.issue_status_file.read_text()) == {
        "ok": True, "reason": "ok", "error_kind": "none", "retryable": False,
        "exists": False, "issue_number": None, "title": "AI Headlines - Sep 8",
    }


@pytest.mark.parametrize(
    ("message", "error_kind", "retryable"),
    [
        ("error connecting to api.github.com", "transient", True),
        ("401 bad credentials", "auth", False),
    ],
)
def test_issue_check_writes_fresh_expected_error(
    artifacts, monkeypatch, message, error_kind, retryable,
):
    def fail_check():
        assert not artifacts.issue_status_file.exists()
        raise RuntimeError(message)

    monkeypatch.setattr(main, "check_issue_status", fail_check)
    with pytest.raises(SystemExit) as exc:
        main._run_check_issue(artifacts, logging.getLogger(__name__))

    assert exc.value.code == 1
    assert json.loads(artifacts.issue_status_file.read_text()) == {
        "ok": False, "reason": message, "error_kind": error_kind,
        "retryable": retryable, "exists": False, "issue_number": None, "title": "",
    }


def test_candidate_export_removes_both_old_files_before_collection(artifacts, monkeypatch):
    def fail_collect():
        assert not artifacts.status_file.exists()
        assert not artifacts.candidates_file.exists()
        raise OSError("collection failed")

    monkeypatch.setattr(graph, "collect_items_with_stats", fail_collect)
    with pytest.raises(OSError, match="collection failed"):
        main._run_candidates_only(artifacts, logging.getLogger(__name__))

    assert not artifacts.status_file.exists()
    assert not artifacts.candidates_file.exists()
    assert json.loads(artifacts.issue_status_file.read_text()) == {"stale": True}


def test_candidate_export_removes_both_old_files_before_graph_import(artifacts, monkeypatch):
    original_import = builtins.__import__

    def fail_graph_import(name, *args, **kwargs):
        if name == "graph":
            assert not artifacts.status_file.exists()
            assert not artifacts.candidates_file.exists()
            raise ImportError("graph dependency broken")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_graph_import)
    with pytest.raises(ImportError, match="graph dependency broken"):
        main._run_candidates_only(artifacts, logging.getLogger(__name__))

    assert not artifacts.status_file.exists()
    assert not artifacts.candidates_file.exists()


@pytest.mark.parametrize("old_files_exist", [False, True])
@pytest.mark.parametrize(
    ("feeds_failed", "reason"),
    [(0, "no_fresh_items"), (1, "empty_snapshot_with_feed_errors"), (2, "feed_fetch_failed")],
)
def test_candidate_export_writes_fresh_empty_snapshot_and_status(
    artifacts, monkeypatch, old_files_exist, feeds_failed, reason,
):
    if not old_files_exist:
        artifacts.status_file.unlink()
        artifacts.candidates_file.unlink()
    feed_errors = [{"source": "Example", "error": "timeout"}] if feeds_failed else []

    def collect():
        assert not artifacts.status_file.exists()
        assert not artifacts.candidates_file.exists()
        return [], {
            "feeds_total": 2, "feeds_succeeded": 2 - feeds_failed,
            "feeds_failed": feeds_failed, "items_collected": 0,
            "feed_errors": feed_errors,
        }

    monkeypatch.setattr(graph, "collect_items_with_stats", collect)
    if feeds_failed:
        with pytest.raises(SystemExit) as exc:
            main._run_candidates_only(artifacts, logging.getLogger(__name__))
        assert exc.value.code == 1
    else:
        main._run_candidates_only(artifacts, logging.getLogger(__name__))

    snapshot = json.loads(artifacts.candidates_file.read_text())
    run_status = json.loads(artifacts.status_file.read_text())
    assert snapshot["schema_version"] == 5
    assert snapshot["groups"] == []
    assert run_status["ok"] is (not feeds_failed)
    assert run_status["reason"] == reason
    assert run_status["feeds_failed"] == feeds_failed
    assert run_status["feed_errors"] == feed_errors


@pytest.mark.parametrize("blocked_output", ["issue_status_file", "status_file", "candidates_file"])
def test_failed_invalidation_stops_producer(artifacts, monkeypatch, blocked_output):
    blocked_path = getattr(artifacts, blocked_output)
    original_unlink = Path.unlink

    def fail_unlink(path, *args, **kwargs):
        if path == blocked_path:
            raise PermissionError("cannot invalidate")
        return original_unlink(path, *args, **kwargs)

    def unexpected_call(*args):
        pytest.fail("producer called after failed invalidation")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    monkeypatch.setattr(main, "check_issue_status", unexpected_call)
    monkeypatch.setattr(graph, "export_candidate_snapshot", unexpected_call)
    run = main._run_check_issue if blocked_output == "issue_status_file" else main._run_candidates_only

    with pytest.raises(PermissionError, match="cannot invalidate"):
        run(artifacts, logging.getLogger(__name__))

    assert json.loads(blocked_path.read_text()) == {"stale": True}
