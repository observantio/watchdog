"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


from services.loki.label_utils import (
    parse_labelset_value,
    normalize_label_value,
    normalize_label_values,
    normalize_label_dict,
)


def test_parse_labelset_value_handles_escaped_quotes_and_backslashes():
    raw = 'app="complex\\"value\\"",env="prod"'
    parsed = parse_labelset_value('app', raw)
    assert parsed and 'app' in parsed
    assert '"' in parsed['app'] or '\\"' in parsed['app']


def test_normalize_label_value_and_dict_and_values():
    nv, parsed = normalize_label_value('app', 'app="web",other="y",')
    assert nv == 'web'
    assert isinstance(parsed, dict) and parsed.get('other') == 'y'

    labels = {'app': 'app="web",other="y",', 'env': 'prod'}
    extras = normalize_label_dict(labels)
    assert extras.get('other') == 'y'
    assert labels['app'].startswith('app=')

    values = ['app="web",other="y",', 'plain']
    cleaned = normalize_label_values('app', values)
    assert 'web' in cleaned and 'plain' in cleaned
