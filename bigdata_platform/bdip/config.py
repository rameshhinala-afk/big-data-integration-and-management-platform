"""Central configuration: where raw sources live and where the warehouse is written."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Config:
    root: Path = DEFAULT_ROOT

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def customers_csv(self) -> Path:
        return self.raw_dir / "customers.csv"

    @property
    def orders_json(self) -> Path:
        return self.raw_dir / "orders.json"

    @property
    def products_db(self) -> Path:
        return self.raw_dir / "products.db"

    @property
    def warehouse_path(self) -> Path:
        return self.root / "warehouse.db"
