from asyncpg.exceptions import UndefinedTableError
from guillotina.db.interfaces import IPostgresStorage
from guillotina.db.storages.pg import watch as watch_pg
from guillotina.db.storages.utils import register_sql
from guillotina.utils import get_current_container
from guillotina.utils import get_current_transaction

import logging
import json

register_sql(
    "FETCH_AMQP_TASK_SUMMARY", 
    f"""
    SELECT * FROM {{table_name}} where task_id = $1
    """
)

logger = logging.getLogger("onna.canonical")


async def fetch_amqp_task_summary(task_id):
    txn = get_current_transaction()
    container_name = get_current_container().id
    table_name = f"{container_name}_amqp_tasks"
    if not IPostgresStorage.providedBy(txn.storage):
        return
    try:
        container_name = get_current_container().id
        table_name = f"{container_name}_amqp_tasks"
        async with txn.storage.pool.acquire() as conn:
            with watch_pg("fetch_amqp_task_summary"):
                row = await conn.fetchrow(
                    txn.storage.sql.get("FETCH_AMQP_TASK_SUMMARY", table_name),
                    task_id,
                )
                if row:
                    summary = json.loads(row.get("summary", "{}"))
                    updated = summary.get("finished_at")
                    return {
                        "result": summary,
                        "status": row.get("status"),
                        "updated": updated
                    }
    except UndefinedTableError:
        logger.warning(f"{{table_name}} has not yet initialized, cannot perform query.")
