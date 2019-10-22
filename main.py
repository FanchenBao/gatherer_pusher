from multiprocessing import Queue, JoinableQueue
from collect_data import collect_data

# from db import initialize, insert_mult_rows
from utility import make_db_insertable_data, internet_on
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
    # DB = f"./database/{args.database}"  # database location
    # TABLE_NAME = args.table_name
    # CREATE_TABLE = f""" CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    #                                     probeId INTEGER PRIMARY KEY,
    #                                     macAddress NVARCHAR(64),
    #                                     isPhysical BOOLEAN,
    #                                     isWifi BOOLEAN,
    #                                     captureTime DATETIME,
    #                                     rssi INTEGER,
    #                                     channel INTEGER
    #                                 ); """
    # schema WITHOUT the autoincremented rowid (i.e. probeId in this context)
    # SCHEMA = "macAddress,isPhysical,isWifi,captureTime,rssi,channel"
    # main.py must be right outside `sniff-probes` folder.
    CMD = f"./sniff-probes.sh -i {args.interface} --channel_hop"
    RETRY_INTERVAL: int = 10  # wait time before retry database connection or spinning up child processes
    TOTAL_RETRIES: int = 5  # Total number of retries allowed.
    MAX_OFFLINE_DUR: int = 60  # Max time allowed to wait for device to go online
    wifi_data_q = Queue()  # transmit data from col_data_proc to here
    msg_q = JoinableQueue()  # inform health of child process

    # main loop
    # reinsert: bool = False  # flag, whether re-inserting row is needed.
    # conn = None  # database connection, default to None
    start_process = True  # flag, whether child processes need to be spun up
    us = UploadService()
    while True:
        if start_process:
            # start probing. Probing never stops
            probe_proc = start_command(
                CMD, "Probe Request Sniffing", RETRY_INTERVAL, TOTAL_RETRIES
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

        # if conn is None:  # initialize database
        #     conn = initialize(DB, CREATE_TABLE, RETRY_INTERVAL, TOTAL_RETRIES)
        #     # if db cannot be initiated after multiple retries, end program.
        #     if not conn:
        #         kill_cmd(probe_proc, "Probe Request Sniffing")
        #         kill_child(col_data_proc, "Data Collection")
        #         sys.exit(1)

        # insertable = ""  # dummy, fix "local variable referenced before assign"
        # while conn and msg_q.empty():
        #     # assign new insertable if there is no need to reinsert
        #     if not reinsert and not wifi_data_q.empty():
        #         insertable = make_db_insertable_data(wifi_data_q.get(), True)
        #     # If error occurs during insertion, retry db connection and set
        #     # `reinsert` to True
        #     if not insert_mult_rows(conn, insertable, TABLE_NAME, SCHEMA):
        #         reinsert = True
        #         conn.close()
        #         conn = None  # indicate error happens at database level
        #         break
        #     else:
        #         reinsert = False

        # error in data collection or probing

        # push data directly to cloud. Currently the pushing frequency is
        # the same as the probing session duration
        offline_timer = 0
        while msg_q.empty():
            if internet_on():  # internet is on, ready to push MQTT message
                offline_timer = 0
                if not us.online:
                    us.connect()

                # add code to push any data from local database to wifi_data_q

                while not wifi_data_q.empty() and us.online:
                    print(f"****** queue size: {wifi_data_q.qsize()} ****")
                    raw_data = wifi_data_q.get()
                    us.send_MQTT(make_db_insertable_data(raw_data, True))
                    timer = 0
                    while not us.msg_sent and timer <= 5:
                        sleep(1)
                        timer += 1
                    if timer < 5:  # msg successfully sent
                        us.msg_sent = False  # set the flag back to false
                    else:  # msg sent failed.
                        logger.info(
                            "MQTT msg not sent. Put back into data queue"
                        )
                        wifi_data_q.put(raw_data)  # put the unsent data back
            # internet is off but we are still waiting
            elif offline_timer <= MAX_OFFLINE_DUR:
                logger.warning(f"Device offline for {offline_timer} seconds")
                offline_timer += 10  # outer loop waits 10s each iteration
                if not us.offline:  # disconnect client if not already
                    us.disconnect()
            else:  # internet is off for too long, push data to database
                logger.info(
                    "Internet off for too long. Pushing data to database"
                )

                # add code to push data from wifi_data_q to local database

            sleep(10)

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
