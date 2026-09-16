"""Execute textbook migration DDL safely in online and offline modes."""

from __future__ import annotations

from alembic import op
from sqlalchemy import DDL


def execute_textbook_ddl(sql: str) -> None:
    if op.get_context().as_sql:
        op.execute(DDL(sql))
        return
    op.get_bind().exec_driver_sql(sql)
