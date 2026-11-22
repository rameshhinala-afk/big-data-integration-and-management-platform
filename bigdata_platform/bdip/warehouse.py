"""SQLite-backed warehouse with a built-in metadata catalog and lineage graph."""

import json
import sqlite3
from datetime import datetime

import pandas as pd


class Warehouse:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self._catalog = []
        self._lineage = []

    def write(self, name, df, layer, source, transformation=None, parents=()):
        """Write a DataFrame as a table and record it in the catalog + lineage."""
        df.to_sql(name, self.conn, if_exists="replace", index=False)
        self._catalog.append({
            "dataset": name, "layer": layer, "source": source,
            "row_count": len(df), "column_count": df.shape[1],
            "columns": json.dumps(list(df.columns)),
            "loaded_at": datetime.now().isoformat(timespec="seconds"),
        })
        for parent in parents:
            self._lineage.append({"target": name, "source": parent,
                                  "transformation": transformation or ""})

    def append(self, name, df):
        df.to_sql(name, self.conn, if_exists="append", index=False)

    def flush_metadata(self):
        pd.DataFrame(self._catalog).to_sql("catalog", self.conn, if_exists="replace", index=False)
        pd.DataFrame(self._lineage).to_sql("lineage", self.conn, if_exists="replace", index=False)
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()
