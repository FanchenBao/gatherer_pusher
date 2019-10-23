# Some code borrowed from https://www.sqlitetutorial.net/sqlite-python/
import sqlite3
from sqlite3 import Error
import logging
import logging.config
import yaml
from time import sleep
from typing import Any, List, Tuple


# set up logger
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
logger = logging.getLogger("db")


def create_connection(db_file):
    """ create a database connection to the SQLite database
        specified by db_file
    :param db_file: database file
    :return: Connection object or None
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        logger.info("Database successfully connected.")
    except Error:
        logger.exception("Error! Cannot establish database connection.")
    return conn


def create_table(conn, create_table_sql) -> bool:
    """ create a table from the create_table_sql statement
    :param conn: Connection object
    :param create_table_sql: a CREATE TABLE statement
    :return: True if table creation succeeds, otherwise false
    """
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
        logger.info("Table successfully created.")
        return True
    except Error:
        logger.exception("Error! Cannot create table.")
        return False


def select_rows(conn, table_name: str, col_names: str, num_rows: int):
    """
    Select {num_rows} from {table_name} with the given {col_names}
    Args:
        conn:           Connection object to database
        table_name:     Name of the table
        col_names:      Column names to be associated with each row. Use '*' to
                        select all columns; otherwise provide a string of col
                        names separated by comma, e.g. 'date, weather, city'
        num_rows:       Number of rows to be selected
    Returns:
        An list of rows selected. If no row is selected, return empty list.
    Raises:
        None
    """
    rows: List[Any] = []
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {col_names} FROM {table_name} LIMIT ?", (num_rows,)
        )
        rows = cur.fetchall()
        logger.info("Successfully executed 'SELECT' query.")
    except Error:
        logger.exception(f"Error! Cannot select rows from {table_name}")
    return rows


def delete_rows(conn, table_name: str, row_id: str, num_rows: int) -> None:
    """
    Delete the top {num_rows} rows sorted by {id}
    Args:
        conn:           Connection object to database
        table_name:     Name of the table
        row_id:         The id column (primary key, autoincremented)
        num_rows:       Number of rows to be deleted
    Returns:
        None
    Raises:
        None
    """
    try:
        cur = conn.cursor()
        cur.execute(
            f"DELETE FROM {table_name} ORDER BY ? LIMIT ?", (row_id, num_rows)
        )
        logger.info(f"Successfully deleted {num_rows} rows.")
    except Error:
        logger.exception(f"Error! Cannot delete rows from {table_name}")


def fetch_rows(conn, table_name, col_names, num_rows) -> List[Tuple[Any, ...]]:
    """
    Extract the top {num_rows} rows from local database (fetch and delete)
    Args:
        conn:           Connection object to database
        table_name:     Name of the table
        col_names:      Column names to be associated with each row. Use '*' to
                        select all columns; otherwise provide a string of col
                        names separated by comma, e.g. 'date, weather, city'
        num_rows:       Number of rows to be fetched
    Return:
        A list of tuples with each tuple representing a row of data. This list
        is known as `insertable` in main.py and is also the element in
        wifi_data_q. After getting `insertable`, the corresponding rows in the
        table are deleted.
    Raises:
        None
    """
    insertable: List[Tuple[Any, ...]] = []
    with conn:
        for r in select_rows(conn, table_name, col_names, num_rows):
            # see doc: https://docs.python.org/3/library/sqlite3.html#sqlite3.Row
            # for a description of sqlite3.Row object.
            insertable.append(tuple(r))
            logger.debug(f"Fetched row: {tuple(r)}")
        if len(insertable) > 0:
            delete_rows(conn, table_name, "probeid", len(insertable))
        else:
            logger.info("Fetched 0 rows")
    return insertable


def insert_row(conn, row_data, table_name, schema) -> bool:
    """
    Insert a row into the database connected with conn
    :param conn: connection object to database
    :param row_data: insertable data repr the row
    :param table_name: name of the table
    :param schema: schema of the table
    :return: True if row insertion succeeds, otherwise false
    """
    sql = f""" INSERT INTO {table_name}({schema})
              VALUES({','.join(['?'] * len(schema.split(',')))}) """
    try:
        cur = conn.cursor()
        cur.execute(sql, row_data)
        logger.debug(f"Row {row_data} successful inserted.")
        return True
    except Error:
        logger.exception(f"Error! Cannot insert row to {table_name}.")
        return False


def insert_mult_rows(
    conn,
    rows: List[Tuple[str, bool, bool, str, int, int]],
    table_name: str,
    schema: str,
) -> bool:
    """
    Insert multiple rows to a database
    Args:
        conn:       Connection to a database
        rows:       A deque of rows to be inserted
        table_name: Name of the table
        schema:     Schema of the table
    Returns:
        True if all insertions are successful, otherwise false
    Raises:
        None
    """
    is_successful: bool = True
    while rows and is_successful:
        is_successful = insert_row(conn, rows.pop(), table_name, schema)
    # commit only after all rows have been inserted
    # If any insertion fails, we will reinsert everything later (this is to
    # accommodate the logic in main.py)
    if is_successful:
        conn.commit()
        sleep(1)
    return is_successful


def initialize(
    DB: str, CREATE_TABLE: str, retry_interval: int, total_retries: int
) -> Any:
    """
    Initialize a database and create a table. If connection to database or table
    creation fails, retry in 10 seconds (default, configurable). No more than 5
    repeated retries allowed (default, configurable)
    Args:
        DB:             Path to the local database.
        CREATE_TABLE:   SQL query to create a table in the database.
        retry_interval: How much time (in seconds) to wait in between reconnect
                        attempts
        total_retries:  Max number of repeated retries allowed
    Return:
        conn:           Object representing aconnected database. Or None if
                        connection fails.
    Raises:
        None
    """
    while total_retries:
        conn = create_connection(DB)
        if conn is None or not create_table(conn, CREATE_TABLE):
            logger.error(
                f"Connecting to database failed. Retry in {retry_interval} seconds."
            )
            total_retries -= 1
            sleep(retry_interval)
        else:
            return conn
    logger.error(
        f"Maximum retry attempts ({total_retries}) exceeded. Database connection cannot be established."
    )
    return None
