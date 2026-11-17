#!/usr/bin/env python3
"""Validate bundled JSON examples."""
import json
from pathlib import Path
assets = Path(__file__).resolve().parents[1] / 'assets'
for filename in ('site-config.example.json', 'treatments.example.json'):
    value = json.loads((assets / filename).read_text(encoding='utf-8'))
    assert isinstance(value, dict)
    print('OK:', filename)
