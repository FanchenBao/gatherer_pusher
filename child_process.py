import logging
import logging.config
import yaml
import sys
from subprocess import Popen, PIPE
from multiprocessing import Process
from time import sleep


# set up logger
with open("logger_config.yaml", "r") as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
logger = logging.getLogger("child_process")


def start_command(CMD: str, name: str, HEALTH_CHECK_CONFIG):
    """
    Run a command in a child process, and pipe its stdout through Popen's PIPE,
    such that the output can be picked up elsewhere in the program

    Args:
        CMD:                    Command to be run.
        name:                   Name of the child process
        HEALTH_CHECK_CONFIG:    Config for TOTAL_RETRIES and RETRY_INTERVAL
    Return:
        An object generated from `Popen`, running the command
    Raises:
        Any exception if `Popen` fails to create a child process
    """
    retries = 0
    TOTAL_RETRIES = int(HEALTH_CHECK_CONFIG["TOTAL_RETRIES"])
    RETRY_INTERVAL = int(HEALTH_CHECK_CONFIG["RETRY_INTERVAL"])
    while retries <= TOTAL_RETRIES:
        try:
            cmd_process = Popen(CMD, shell=True, stdout=PIPE, bufsize=1)
            logger.info(f"{name} process successfully created!")
            return cmd_process
        except Exception:
            logger.exception(f"Error! Cannot start {name} process.")
            retries += 1
            sleep(RETRY_INTERVAL)
    logger.error(
        f"Maximum retry attempts ({TOTAL_RETRIES}) exceeded. {name} process cannot be created."
    )
    sys.exit(1)


def start_child(func, name: str, HEALTH_CHECK_CONFIG, *args):
    """
    Start a child process running `func` with arguments input from `args`

    Args:
        func:                   The function to be run in the child process.
        name:                   Name of the child process.
        HEALTH_CHECK_CONFIG:    Config for TOTAL_RETRIES and RETRY_INTERVAL
        args:                   List of arguments to be passed to func
    Return:
        An object generated from `Process`, running `func`.
    Raises:
        Any exception if `Process` fails to create a child process
    """
    child_proc = Process(target=func, args=args)
    TOTAL_RETRIES = int(HEALTH_CHECK_CONFIG["TOTAL_RETRIES"])
    RETRY_INTERVAL = int(HEALTH_CHECK_CONFIG["RETRY_INTERVAL"])
    retries = 0
    while retries <= TOTAL_RETRIES:
        try:
            child_proc.start()
            logger.info(f"{name} process successfully created!")
            return child_proc
        except Exception:
            logger.exception(f"Error! Cannot start {name} process.")
            retries += 1
            sleep(RETRY_INTERVAL)
    logger.error(
        f"Maximum retry attempts ({TOTAL_RETRIES}) exceeded. {name} process cannot be created."
    )
    sys.exit(1)


def kill_child(process, name: str, msg_q):
    """
    Utility function to kill a child process spun up from a python function.
    Specifically, a "Kill Imminent" signal is sent to the child process, such
    that it can finish up its job first before being killed.

    Args:
        process:        A child process spun up from a python function.
        name:           Name of the process.
        msg_q:          A JoinableQueue to warn the process of imminent kill.
    Returns:
        None
    Raises:
        None
    """
    if process.is_alive():
        msg_q.put("Kill Imminent")
        msg_q.join()  # block until col_data_proc finishes handling the remaining data
        process.terminate()
        process.join()
    logger.info(f"Child process {name} has been terminated")


def kill_cmd(process, name: str):
    """
    Utility function to kill a child process spun up from a bash command.

    Args:
        process:        A child process spun up from a bash command.
        name:           Name of the process
    Returns:
        None
    Raises:
        None
    """
    if process.poll() is None:
        process.kill()
        process.wait()
    logger.info(f"Child process {name} has been killed")
