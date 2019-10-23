from collections import defaultdict
from time import time
import re
from utility import make_data_chunk, make_db_insertable_data
import logging
import logging.config
import yaml


# set up logger
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
logger = logging.getLogger("collect_data")


def collect_data(probe_proc, data_q, msg_q, sess_dur):
    """
    Collect data (done in a separate process) provided by sniff-probes.sh
    and push each data_chunk to the main process every sess_dur seconds

    Args:
        probe_proc: A subprocess running `sniff-probes.sh` that pipes out its output.
        q:          A queue for communication between the child running this function
                    and its parent.
        sess_dur:   Duration of a monitoring session before the data chunk
                    currently collected is pushed to q.
    Returns:
        None
    Raises:
        None
    """
    data_chunk = defaultdict(dict)
    start_time = time()

    # read output from sniff-probes line by line. See SO discussion below for details
    # https://stackoverflow.com/questions/803265/getting-realtime-output-using-subprocess
    try:
        for line in iter(probe_proc.stdout.readline, b""):
            decoded_line = line.decode("utf-8").strip()
            if decoded_line.isnumeric():  # switch to a new channel
                curr_channel = int(decoded_line)
            else:
                # parse the output. Note that there is no more data parsing in sniff-probes
                m = re.match(
                    r"(\d{4}-\d{2}-\d{2}\s\d{2}\:\d{2}\:\d{2}\.\d{3}).+(-\d+)dBm.+SA((\:[0-9a-f]{2}){6})",
                    decoded_line,
                )
                make_data_chunk(
                    data_chunk,
                    curr_channel,
                    m.group(3)[1:],
                    int(m.group(2)),
                    m.group(1),
                )
            # every sess_dur time, we process data_chunk and push the processed
            # data to q.
            if time() - start_time >= sess_dur:
                start_time = time()
                data_q.put(make_db_insertable_data(data_chunk, True))
                data_chunk.clear()
            # This is for the special situation where probe_proc is to be killed
            # while everything else is running fine. We will send out the last
            # chunk of data before killing col_data_proc.
            if not msg_q.empty() and msg_q.get() == "Kill Imminent":
                if len(data_chunk):
                    data_q.put(make_db_insertable_data(data_chunk, True))
                msg_q.task_done()  # signal to main process that collect_data can be killed
                break
    except Exception:
        logger.info(f"current line read from probe_proc: {decoded_line}")
        logger.exception(
            "Error! Unable to read output from probing process. Data collection failed."
        )
        msg_q.put("fail")  # notify parent process
        msg_q.join()
