"""Read and write the golden set as JSONL, validating every item."""
import json
from dataclasses import asdict, fields

from insurance_automation.contracts import ROUTES, TOOL_NAMES
from insurance_automation.evaluation.types import GoldenItem

SPLITS = ('dev', 'heldout')
_REQUIRED = [f.name for f in fields(GoldenItem)]


def _parse(line: str, number: int) -> GoldenItem:
    data = json.loads(line)
    missing = [name for name in _REQUIRED if name not in data]
    if missing:
        raise ValueError(f'line {number}: missing fields {missing}')
    item = GoldenItem(**{name: data[name] for name in _REQUIRED})
    if item.expected_route not in ROUTES:
        raise ValueError(f'{item.id}: unknown route {item.expected_route!r}')
    unknown = [t for t in item.expected_tools if t not in TOOL_NAMES]
    if unknown:
        raise ValueError(f'{item.id}: unknown tool names {unknown}')
    if item.split not in SPLITS:
        raise ValueError(f'{item.id}: split must be one of {SPLITS}, got {item.split!r}')
    return item


def load_golden(path: str, split: str | None = None) -> list[GoldenItem]:
    items: list[GoldenItem] = []
    seen: set[str] = set()
    with open(path, encoding='utf-8') as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            item = _parse(line, number)
            if item.id in seen:
                raise ValueError(f'duplicate id {item.id!r}')
            seen.add(item.id)
            items.append(item)
    return [i for i in items if split is None or i.split == split]


def save_golden(items: list[GoldenItem], path: str) -> None:
    with open(path, 'w', encoding='utf-8') as handle:
        handle.writelines(json.dumps(asdict(item), ensure_ascii=False) + '\n' for item in items)
