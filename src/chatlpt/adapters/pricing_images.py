"""The image price table (per megapixel), loaded from a JSON file with provenance (D25)."""

import json
from pathlib import Path

from chatlpt.contracts import ImagePriceTable
from chatlpt.errors import InvalidRequest


class FileImagePriceSource:
    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise InvalidRequest(f"image pricing file {path} not found (CHATLPT_IMAGE_PRICING_FILE)")
        self._table = ImagePriceTable.model_validate(json.loads(path.read_text()))

    def table(self) -> ImagePriceTable:
        return self._table
