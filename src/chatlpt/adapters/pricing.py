"""The retail price table, loaded from a JSON file with provenance (D4, docs/references/qwen-pricing.md)."""

import json
from pathlib import Path

from chatlpt.contracts import PriceTable
from chatlpt.errors import InvalidRequest


class FilePriceSource:
    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise InvalidRequest(f"pricing file {path} not found (CHATLPT_PRICING_FILE)")
        self._table = PriceTable.model_validate(json.loads(path.read_text()))

    def table(self) -> PriceTable:
        return self._table
