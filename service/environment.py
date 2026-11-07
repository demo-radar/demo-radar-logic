"""Strict readers for process settings; errors never include supplied values."""

import os

from pydantic import ConfigDict, FiniteFloat, StrictInt, TypeAdapter

SETTINGS_VALIDATION = ConfigDict(
    strict=True, hide_input_in_errors=True, allow_inf_nan=False, extra="forbid"
)
_NUMBER_VALIDATORS = {int: TypeAdapter(StrictInt), float: TypeAdapter(FiniteFloat)}


def env_bool(name, default=False):
    value = os.environ.get(name, str(default)).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def env_number(name, default, *, kind=int):
    try:
        return _NUMBER_VALIDATORS[kind].validate_python(kind(os.environ.get(name, str(default))))
    except (ValueError, OverflowError):
        raise ValueError(f"{name} must be a finite {kind.__name__}") from None
