"""Decode BOSS salary numerals while keeping unknown encodings visible as unknown.

The current BOSS list font maps U+E031..U+E03A to 0..9. The mapping is
specific to that observed font range; a new range must be verified separately.
"""

from __future__ import annotations

import re


UNKNOWN_SALARY = "薪资待解析"
_BOSS_DIGITS = {chr(0xE031 + digit): str(digit) for digit in range(10)}
_PRIVATE_USE = re.compile(r"[\ue000-\uf8ff]")


def readable_salary(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not _PRIVATE_USE.search(raw):
        return raw
    if any(char not in _BOSS_DIGITS for char in raw if _PRIVATE_USE.fullmatch(char)):
        return UNKNOWN_SALARY
    decoded = "".join(_BOSS_DIGITS.get(char, char) for char in raw)
    # Catch an incorrect or changed font mapping before showing implausible pay.
    numbers = re.findall(r"\d+(?:\.\d+)?", decoded)
    if not numbers or not re.search(r"(?:K|k|千|万|元)", decoded):
        return UNKNOWN_SALARY
    if len(numbers) >= 2 and float(numbers[0]) > float(numbers[1]):
        return UNKNOWN_SALARY
    if any(float(number) > 1000000 for number in numbers[:2]):
        return UNKNOWN_SALARY
    return decoded
