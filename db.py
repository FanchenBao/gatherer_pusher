# Some code borrowed from https://www.sqlitetutorial.net/sqlite-python/
import sqlite3
from sqlite3 import Error
import logging
import logging.config
import yaml
from time import sleep
from typing import Any, List, Tuple


# set up logger
with open("logger_config.yaml", "r") as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
logger = logging.getLogger("db")


class SQLiteDB:
    def __init__(self, DB_CONFIG, HEALTH_CHECK_CONFIG):
        self.DB_LOC = DB_CONFIG["DB_LOC"]
        self.TABLE = DB_CONFIG["TABLE"]
        self.ROW_ID = DB_CONFIG["ROW_ID"]
        self.SCHEMA = DB_CONFIG["SCHEMA"]
        self.RETRY_INTERVAL = int(HEALTH_CHECK_CONFIG["RETRY_INTERVAL"])
        self.TOTAL_RETRIES = int(HEALTH_CHECK_CONFIG["TOTAL_RETRIES"])
        self.conn = None
        self.initialize()

    def initialize(self) -> bool:
        """
        Initialize a database and create a table. If connection to database or table
        creation fails, retry in 10 seconds (default, configurable). No more than 5
        repeated retries allowed (default, configurable)

        Return:
            True if db initialization succeeds. Otherwise, False
        """
        retries = 0
        while retries <= self.TOTAL_RETRIES:
            self.create_connection()
            if self.conn is None or not self.create_table():
                logger.error(
                    f"Connecting to database failed. Retry in {self.RETRY_INTERVAL} seconds."
                )
                retries -= 1
                sleep(self.RETRY_INTERVAL)
            else:
                return True
        logger.error(
            f"Maximum retry attempts ({self.TOTAL_RETRIES}) exceeded. Database connection cannot be established."
        )
        return False

    def create_connection(self) -> None:
        """ create a database connection to the SQLite database
        """
        try:
            self.conn = sqlite3.connect(self.DB_LOC)
            # this allows each fetched row to be used as dict
            # see here: https://docs.python.org/3.7/library/sqlite3.html#row-objects
            self.conn.row_factory = sqlite3.Row
            logger.info("Database successfully connected.")
        except Error:
            logger.exception("Error! Cannot establish database connection.")

    def create_table(self) -> bool:
        """ create a table
        :return: True if table creation succeeds, otherwise false
        """
        CREATE_TABLE = f""" CREATE TABLE IF NOT EXISTS {self.TABLE} (
                                        probeId INTEGER PRIMARY KEY,
                                        macAddress NVARCHAR(64),
                                        isPhysical BOOLEAN,
                                        isWifi BOOLEAN,
                                        captureTime DATETIME,
                                        rssi INTEGER,
                                        channel INTEGER
                                    ); """
        try:
            c = self.conn.cursor()
            c.execute(CREATE_TABLE)
            logger.info("Table successfully created.")
            return True
        except Error:
            logger.exception("Error! Cannot create table.")
            return False

    def close_connection(self) -> None:
        """ close the db connection """
        try:
            self.conn.close()
            self.conn = None
            logger.info("Database successfully closed.")
        except Error:
            logger.exception("Error! Cannot close database connection.")

    def is_connected(self) -> bool:
        """ Return True if db connection is on, otherwise False """
        return self.conn is not None

    def select_rows(self, col_names: str, num_rows: int) -> List[Any]:
        """
        Select {num_rows} from the table with given {col_names}
        Args:
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
            cur = self.conn.cursor()
            cur.execute(
                f"SELECT {col_names} FROM {self.TABLE} LIMIT ?", (num_rows,)
            )
            rows = cur.fetchall()
            logger.info(f"Successfully selected {len(rows)} rows.")
        except Error:
            logger.exception(f"Error! Cannot select rows from {self.TABLE}")
        return rows

    def insert_row(self, row_data) -> bool:
        """
        Insert a row into the database connected with conn.
        *******  NOTE This function DOES NOT COMMIT!!  ******
        :param row_data: insertable data repr the row
        :return: True if row insertion succeeds, otherwise false
        """
        sql = f""" INSERT INTO {self.TABLE}({self.SCHEMA})
                  VALUES({','.join(['?'] * len(self.SCHEMA.split(',')))}) """
        try:
            cur = self.conn.cursor()
            cur.execute(sql, row_data)
            logger.debug(f"Row {row_data} successful inserted.")
            return True
        except Error:
            logger.exception(f"Error! Cannot insert row to {self.TABLE}.")
            return False

    def delete_rows(self, num_rows: int) -> None:
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
            cur = self.conn.cursor()
            cur.execute(
                f"DELETE FROM {self.TABLE} ORDER BY ? LIMIT ?",
                (self.ROW_ID, num_rows),
            )
            logger.info(f"Successfully deleted {num_rows} rows.")
        except Error:
            logger.exception(f"Error! Cannot delete rows from {self.TABLE}")

    def fetch_rows_all_col(
        self, num_rows: int
    ) -> List[Tuple[str, bool, bool, str, int, int]]:
        """
        Extract the top {num_rows} rows from local database (fetch and delete)
        Args:
            num_rows:       Number of rows to be fetched
        Return:
            A list of tuples with each tuple representing a row of data. After
            getting all the rows, the corresponding rows in the table are deleted.
        Raises:
            None
        """
        rows: List[Tuple[str, bool, bool, str, int, int]] = []
        with self.conn:
            for r in self.select_rows(self.SCHEMA, num_rows):
                # see doc: https://docs.python.org/3/library/sqlite3.html#sqlite3.Row
                # for a description of sqlite3.Row object.
                row = (
                    r["macAddress"],
                    r["isPhysical"] == 1,
                    r["isWifi"] == 1,
                    r["captureTime"],
                    int(r["rssi"]),
                    int(r["channel"]),
                )
                logger.debug(f"Fetched row: {row}")
                rows.append(row)
            if len(rows) > 0:
                self.delete_rows(len(rows))
            else:
                logger.info("Fetched 0 rows")
        return rows

    def insert_mult_rows(
        self, rows: List[Tuple[str, bool, bool, str, int, int]]
    ) -> bool:
        """
        Insert multiple rows to a database

        Args:
            rows:       A deque of rows to be inserted
        Returns:
            False if an error occurs during insertion, otherwise True. This
            means if nothing is inserted, i.e. `rows` is empty, the return value
            is still True, because that is not an error.
        Raises:
            None
        """
        is_successful: bool = True
        num_rows: int = len(rows)
        while rows and is_successful:
            is_successful = self.insert_row(rows.pop())
        # commit only after all rows have been inserted
        # If any insertion fails, we will reinsert everything later (this is to
        # accommodate the logic in main.py)
        if is_successful:
            self.conn.commit()
            logger.info(f"Successfully inserted {num_rows} rows to local DB.")
            sleep(1)
        return is_successful

    def push_to_queue(self, data_q, num_rows: int):
        """
        Extract {num_rows} rows from db and put them row by row in a queue.

        Args:
            data_q:         A queue into which the rows are to be pushed
            num_rows:       Number of rows to extract and put in queue
        Returns:
            True if some rows are pushed, False if no row is pushed. In other
            words, True indicates there might still be rows left in the localDB;
            False indicates localDB is empty. Note that the return value here
            does NOT indicate success or failure.
        Raises:
            None
        """
        row_pushed: bool = True  # flag
        if self.is_connected():
            # each rows cannot exceed BATCH_SIZE number of rows
            rows = self.fetch_rows_all_col(num_rows)
            if not rows:
                row_pushed = False
            while rows:
                data_q.put(rows.pop())
        return row_pushed

    def extract_from_queue(self, data_q):
        """
        Extract all data rows from data_q and put them in local db for stable
        storage. If extraction fails, put the data back into data_q.

        Args:
            data_q:     A queue from which rows are extracted.
        Returns:
            False if some error occurs during row insertion to localDB,
            otherwise True. This means if nothing gets inserted to localDB, i.e.
            data_q is empty, we still return True, because this is not an error.
        Raises:
            None
        """
        if not self.is_connected():  # initialize database if necessary
            self.initialize()
        # collect all rows into a list
        rows: List[Tuple[str, bool, bool, str, int, int]] = []
        while not data_q.empty():
            rows.append(data_q.get())
        # insert all rows to local db
        insert_success = self.insert_mult_rows(rows)
        if not insert_success:  # insertion failed
            logger.info("Insert data to db failed. Put back into data queue")
            while rows:
                data_q.put(rows.pop())  # put the unsent data back
        return insert_success
