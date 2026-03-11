from __future__ import annotations

from tests._env import ensure_test_env

ensure_test_env()

from services.loki import label_utils


def test_parse_pairs_skips_invalid_keys_and_handles_escape_sequences():
    parsed = label_utils._parse_pairs('bad key="skip",valid="line\\nnext",path="c:\\\\tmp",tail="slash\\"')

    assert "bad key" not in parsed
    assert parsed["valid"] == "line\nnext"
    assert parsed["path"] == "c:\\tmp"
    assert parsed["tail"] == 'slash"'


def test_parse_pairs_covers_invalid_key_skip_all_escape_kinds_and_trailing_backslash():
    parsed = label_utils._parse_pairs(' ,$bad="skip",good="one\\rtwo\\tthree\\x",tail="end\\')

    assert "$bad" not in parsed
    assert parsed["good"] == "one\rtwo\tthreex"
    assert parsed["tail"] == "end\\"


def test_parse_pairs_stops_on_malformed_segments_and_parse_labelset_injects_label_key():
    assert label_utils._parse_pairs('broken="ok",missingquote=nope') == {"broken": "ok"}
    assert label_utils._parse_pairs('broken="ok",other value') == {"broken": "ok"}

    assert label_utils.parse_labelset_value("service", 123) is None
    injected = label_utils.parse_labelset_value("service", 'payments",env="prod"')
    assert injected == {"service": "payments", "env": "prod"}


def test_normalize_label_value_dict_and_values_cover_fallback_paths(monkeypatch):
    assert label_utils.normalize_label_value("service", object()) == (None, None)

    monkeypatch.setattr(label_utils, "parse_labelset_value", lambda label, value: None)
    assert label_utils.normalize_label_value("service", 'payments",env="prod",') == ("payments", None)

    labels = {"service": 'service="api",env="prod",', "env": "existing"}
    extras = label_utils.normalize_label_dict(labels)
    assert extras == {}

    monkeypatch.setattr(label_utils, "parse_labelset_value", lambda label, value: {"other": "x"})
    assert label_utils.normalize_label_values("service", ['service="api",env="prod",', "plain"]) == ['service="api', "plain"]