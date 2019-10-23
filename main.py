from multiprocessing import Queue, JoinableQueue
from collect_data import collect_data

from db import initialize, insert_mult_rows, fetch_rows
from utility import internet_on
from child_process import start_command, start_child, kill_child, kill_cmd
from time import sleep
import argparse
import logging
import logging.config
import yaml
import os
from upload_service import UploadService

# import sys


def command_line_parser():
    """
    Parse command line arguments
    Args:
        None
    Return:
        A namespace containing all command line arguments.
    Raises:
        None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        dest="interface",
        default="wlan1",
        help="WiFi interface on monitor mode. Default: wlan1",
    )
    parser.add_argument(
        "-s",
        dest="session_duration",
        default=60,
        type=int,
        help="Duration of a monitoring session, in seconds. Default: 60",
    )
    parser.add_argument(
        "-d",
        dest="database",
        default="mobintel.db",
        help="Name of the local sqlite database. Default: mobintel.db",
    )
    parser.add_argument(
        "-t",
        dest="table_name",
        default="Probes",
        help="Name of the table recording probe requests in the local sqlite database. Default: Probes",
    )
    args = parser.parse_args()
    return args


def main(logger):
    # parse command line arguments, if any
    args = command_line_parser()
    try:  # Make a directory called "database" to store db
        os.mkdir(f"./database")
    except OSError:  # folder already there. Catch the exception but do nothing.
        pass

    SESS_DUR = args.session_duration  # monitoring session duration
    DB = f"./database/{args.database}"  # database location
    TABLE_NAME = args.table_name
    CREATE_TABLE = f""" CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                                        probeId INTEGER PRIMARY KEY,
                                        macAddress NVARCHAR(64),
                                        isPhysical BOOLEAN,
                                        isWifi BOOLEAN,
                                        captureTime DATETIME,
                                        rssi INTEGER,
                                        channel INTEGER
                                    ); """
    # schema WITHOUT the autoincremented rowid (i.e. probeId in this context)
    SCHEMA = "macAddress,isPhysical,isWifi,captureTime,rssi,channel"
    SNIFF_CMD = f"./sniff-probes.sh -i {args.interface} --channel_hop"
    RETRY_INTERVAL: int = 10  # wait time before retry database connection or spinning up child processes
    TOTAL_RETRIES: int = 5  # Total number of retries allowed.
    MAX_OFFLINE_DUR: int = 60  # Max time allowed to wait for device to go online
    MAX_ROWS: int = 500  # Max number of rows that can be sent via MQTT in one shot

    wifi_data_q = Queue()  # transmit data from col_data_proc to here
    msg_q = JoinableQueue()  # inform health of child process
    # local database connection
    conn = initialize(DB, CREATE_TABLE, RETRY_INTERVAL, TOTAL_RETRIES)
    start_process = True  # flag, whether child processes need to be spun up
    us = UploadService()
    offline_timer = 0  # record duration that the device is off internet
    while True:
        if start_process:
            # start probing. Probing never stops
            probe_proc = start_command(
                SNIFF_CMD, "Probe Request Sniff", RETRY_INTERVAL, TOTAL_RETRIES
            )
            # start data collection
            col_data_proc = start_child(
                collect_data,
                "Data Collection",
                RETRY_INTERVAL,
                TOTAL_RETRIES,
                probe_proc,
                wifi_data_q,
                msg_q,
                SESS_DUR,
            )
            start_process = False

        # push data directly to cloud. Currently the pushing frequency is
        # the same as the probing session duration
        while msg_q.empty():
            if internet_on():  # internet is on, ready to push MQTT message
                offline_timer = 0
                if not us.online:
                    us.connect()

                while conn is not None:  # extract all data from db
                    # each insertable cannot exceed MAX_ROWS number of rows
                    insertable = fetch_rows(conn, TABLE_NAME, SCHEMA, MAX_ROWS)
                    if insertable:
                        wifi_data_q.put(insertable)
                    else:
                        # when no more data can be extracted from db, close db
                        conn.close()
                        conn = None
                        break

                while not wifi_data_q.empty() and us.online:
                    logger.debug(
                        f"**** queue size: {wifi_data_q.qsize()} ****"
                    )
                    insertable = wifi_data_q.get()
                    if not us.send_MQTT(insertable):  # msg sent failed.
                        logger.info(
                            "MQTT msg not sent. Put back into data queue"
                        )
                        wifi_data_q.put(insertable)  # put the unsent data back
                        logger.info("Close MQTT client connection and retry")
                        us.disconnect()

            # internet is off but we are still waiting
            elif offline_timer <= MAX_OFFLINE_DUR:
                logger.warning(f"Device offline for {offline_timer} seconds")
                offline_timer += 5  # outer loop waits 10s each iteration
                if not us.offline:  # disconnect client if not already
                    us.disconnect()

            else:  # internet is off for too long, push data to database
                logger.info(
                    "Internet off for too long. Pushing data to database"
                )
                if conn is None:  # initialize database
                    conn = initialize(
                        DB, CREATE_TABLE, RETRY_INTERVAL, TOTAL_RETRIES
                    )
                while not wifi_data_q.empty() and conn:
                    logger.debug(
                        f"**** queue size: {wifi_data_q.qsize()} ****"
                    )
                    insertable = wifi_data_q.get()
                    # insert data to local db
                    if not insert_mult_rows(
                        conn, insertable, TABLE_NAME, SCHEMA
                    ):
                        # insertion failed
                        logger.info(
                            "Insert data to db failed. Put back into data queue"
                        )
                        wifi_data_q.put(insertable)  # put the unsent data back
                        logger.info("Close db connection and retry")
                        conn.close()
                        conn = None

            sleep(5)

        if not msg_q.empty() and msg_q.get() == "fail":
            msg_q.task_done()
            kill_cmd(probe_proc, "Probe Request Sniffing")
            kill_child(col_data_proc, "Data Collection")
            logger.info("Retry probing and data collection in 10 seconds")
            start_process = True
        # if conn is None:  # error in database
        #     logger.info("Reconnect to database in 10 seconds")
        sleep(10)


# main driver
if __name__ == "__main__":
    # set up logger
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    logger = logging.getLogger("main")
    main(logger)
