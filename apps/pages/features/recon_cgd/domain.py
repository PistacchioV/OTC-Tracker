# -*- coding: utf-8 -*-
"""As regras da casca — puras."""
import re


def emails(txt):
    return [e.strip() for e in re.split(r'[;,]', str(txt or '')) if e.strip()]
