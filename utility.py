from collections import defaultdict
from hashlib import blake2b
from typing import Dict, List, Any, Tuple
import http.client as httplib


def internet_on():  # borrowed from https://stackoverflow.com/a/29854274/9723036
    """ Check whether internet is on """
    conn = httplib.HTTPConnection("www.google.com", timeout=5)
    try:
        conn.request("HEAD", "/")
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def make_data_chunk(
    data_chunk: Dict[int, Dict[str, Dict[str, List[Any]]]],
    channel: int,
    mac_address: str,
    rssi: int,
    captureTime: str,
):
    """
    Preprocess data by pushing channel, mac_address, rssi, and captureTime
    into data_chunk, such that data_chunk reflects this structure:
    {channel: {mac_address: {'rssi': [], 'captureTime': []}}}
    Used in collect_data.py

    Args:
        data_chunk:     First level key is channel, second level key mac_address,
                        third level keys 'rssi' and 'captureTime'.
        channel:        The channel where the probe request is captured.
        mac_address:    The MAC address of the device making probe request.
        rssi:           Signal strength of the probe request.
        captureTime:    FIRST time a mac_address is seen on this specific channel.
    Returns:
        None
    Raises:
        None
    """
    if mac_address not in data_chunk[channel]:
        data_chunk[channel][mac_address] = defaultdict(list)
    data_chunk[channel][mac_address]["rssi"].append(rssi)
    if not data_chunk[channel][mac_address]["captureTime"]:
        data_chunk[channel][mac_address]["captureTime"].append(captureTime)


def hash_mac(mac_address: str) -> str:
    """
    Produce a hash for mac_address, with salt included.

    Args:
        mac_address: mac address of the device whose probe request is captured
    Returns:
        64-bit hashed version of mac_address, along with its salt.
    Raises:
        None
    """
    SALT = "2ZbaDDdb".encode("utf-8")  # This salt MUST NOT change!
    h_addr = blake2b(digest_size=32, salt=SALT)
    h_addr.update(mac_address.encode("utf-8"))
    return h_addr.hexdigest()


def make_db_insertable_data(
    data_chunk: Dict[int, Dict[str, Dict[str, List[Any]]]], is_wifi: bool
) -> List[Tuple[str, bool, bool, str, int, int]]:
    """
    Process data_chunk to generate a list of tuples that are insertable to sqlite

    Args:
        data_chunk: Preprocessed data coming from data collection, containing
                    data structure like this:
                    {channel: {mac_address: {'rssi': [], 'captureTime': []}}}
    Returns:
        A list of tuples, in which each tuple is a piece of insertable data to
        "Probes" table in "mobintel" database
    Raises:
        None
    """
    insertable: List[Tuple[str, bool, bool, str, int, int]] = []
    for channel, mac_dict in data_chunk.items():
        for mac_address, v in mac_dict.items():
            insertable.append(
                (
                    # hash_mac(mac_address),
                    mac_address,
                    bin(int(mac_address[:2], 16))[-2] == "0",  # '0' = unique
                    is_wifi,
                    v["captureTime"][0],
                    sum(v["rssi"]) // len(v["rssi"]),
                    channel,
                )
            )
    return insertable
