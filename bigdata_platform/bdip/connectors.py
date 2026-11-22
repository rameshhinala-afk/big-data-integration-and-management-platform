"""Source connectors: one small class per source type, all exposing `read() -> DataFrame`."""

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class Connector(ABC):
    def __init__(self, path):
        self.path = Path(path)

    @property
    @abstractmethod
    def kind(self) -> str: ...

    @abstractmethod
    def read(self) -> pd.DataFrame: ...

    def describe(self) -> str:
        return f"{self.kind}:{self.path.name}"


class CSVConnector(Connector):
    kind = "csv"

    def read(self) -> pd.DataFrame:
        # Read everything as text so cleaning is explicit and nothing is silently coerced.
        return pd.read_csv(self.path, dtype=str, keep_default_na=False)


class JSONConnector(Connector):
    kind = "json"

    def read(self) -> pd.DataFrame:
        with open(self.path, encoding="utf-8") as f:
            return pd.DataFrame(json.load(f))


class SQLiteConnector(Connector):
    kind = "sqlite"

    def __init__(self, path, table):
        super().__init__(path)
        self.table = table

    def read(self) -> pd.DataFrame:
        conn = sqlite3.connect(self.path)
        try:
            return pd.read_sql_query(f'SELECT * FROM "{self.table}"', conn)
        finally:
            conn.close()

    def describe(self) -> str:
        return f"{self.kind}:{self.path.name}#{self.table}"
