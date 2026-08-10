from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Field:
    fieldname: str
    fieldtype: str
    label: str | None = None
    options: str | None = None
    reqd: int = 0
    read_only: int = 0
    hidden: int = 0


@dataclass
class DocType:
    name: str
    module: str | None
    source: str
    is_child_table: int = 0
    fields: list[Field] = field(default_factory=list)


@dataclass
class WhitelistedMethod:
    dotted_path: str
    source: str
    method: str
    app: str
    methods: list[str] = field(default_factory=list)
    allow_guest: bool = False
    parameters: list[dict[str, Any]] = field(default_factory=list)


def serialize(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {k: serialize(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [serialize(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value
