from multiprocessing import Queue, JoinableQueue
from collect_data import collect_data
import db
from utility import internet_on, convert_to_payload_test
from child_process import start_command, start_child, kill_child, kill_cmd
from time import sleep
import argparse
import logging
import logging.config
import yaml
import os
import upload_service
import configparser


# set up logger
with open("logger_config.yaml", "r") as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
logger = logging.getLogger("main")


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
    args = parser.parse_args()
    return args


def main():
    # parse command line arguments, if any
    args = command_line_parser()
    SESS_DUR = args.session_duration  # monitoring session duration
    SNIFF_CMD = f"./sniff-probes.sh -i {args.interface} --channel_hop"

    # load app config
    APP_CONFIG = configparser.ConfigParser()
    APP_CONFIG.read("app_config.ini")
    DB_CONFIG = APP_CONFIG["sqlite"]
    HEALTH_CHECK_CONFIG = APP_CONFIG["health_check"]
    AWS_IOT_CONFIG = APP_CONFIG["aws_iot"]

    # Make a directory called "database" to store db
    try:
        os.mkdir(f"./database")
    except OSError:  # folder already there. Catch the exception but do nothing.
        pass

    # Key data structures
    data_q = Queue()  # transmit data from col_data_proc to here
    msg_q = JoinableQueue()  # inform health of child process
    localDB = db.SQLiteDB(DB_CONFIG, HEALTH_CHECK_CONFIG)  # local database
    us = upload_service.UploadService(AWS_IOT_CONFIG)  # aws iot MQTT client
    start_process = True  # flag, whether child processes need to be spun up
    offline_timer = 0  # record duration that the device is off internet

    # main loop
    while True:
        if start_process:
            # start probing. Probing never stops
            probe_proc = start_command(
                SNIFF_CMD, "Probe Request Sniff", HEALTH_CHECK_CONFIG
            )
            # start data collection
            col_data_proc = start_child(
                collect_data,
                "Data Collection",
                HEALTH_CHECK_CONFIG,
                probe_proc,
                data_q,
                msg_q,
                SESS_DUR,
            )
            start_process = False

        # push data directly to cloud if there is internet connection. Otherwise
        # store data in local db and wait for internet to come back.
        while msg_q.empty():
            if internet_on():  # internet is on, ready to push MQTT message
                offline_timer = 0
                if not us.online:
                    us.connect()

                # check to see if there is anything remaining in localDB
                # If there is, take at most BATCH_SIZE of them out each time
                # If not, close localDB
                if not localDB.push_to_queue(
                    data_q, int(AWS_IOT_CONFIG["BATCH_SIZE"])
                ):
                    localDB.close_connection()

                # send a batch of data from data_q to aws iot. If sending faiks
                # disconnect with MQTT client and try again
                if not us.send_MQTT(data_q, convert_to_payload_test):
                    logger.info("Close MQTT client connection and retry")
                    us.disconnect()

            # internet is off but we are still waiting
            elif offline_timer <= int(HEALTH_CHECK_CONFIG["MAX_OFFLINE_DUR"]):
                if offline_timer % 10 == 0:
                    logger.warning(
                        f"Device offline for {offline_timer} seconds"
                    )
                offline_timer += 1  # outer loop waits 10s each iteration
                if not us.offline:  # disconnect client if not already
                    us.disconnect()

            # internet is off for too long, push all data from queue (if
            # available) to localDB for stable storage. If such push fails,
            # close localDB and try again.
            elif not data_q.empty():
                logger.info("Internet off for too long. Push data to database")
                if not localDB.extract_from_queue(data_q):
                    logger.info("Close db connection and retry")
                    localDB.close_connection()

            sleep(1)

        # This code is hit whenever a "fail" message is pushed to `msg_q`
        if not msg_q.empty() and msg_q.get() == "fail":
            msg_q.task_done()
            kill_cmd(probe_proc, "Probe Request Sniffing")
            kill_child(col_data_proc, "Data Collection")
            logger.info("Retry probing and data collection in 10 seconds")
            start_process = True
        sleep(10)


# main driver
if __name__ == "__main__":
    main()
