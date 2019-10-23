from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import json
from time import sleep
import logging
import logging.config
import yaml
from typing import List, Tuple

# set up logger
with open("logger_config.yaml", "r") as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
logger = logging.getLogger("AWSIoTPythonSDK.core")


class UploadService:
    """ A class to handle uploading probe request data via MQTT to aws IoT.
    """

    def __init__(self, AWS_IOT_CONFIG):
        # Create, configure, and connect a MQTT client.
        self.myAWSIoTMQTTClient = AWSIoTMQTTClient(AWS_IOT_CONFIG["CLIENT_ID"])
        self.myAWSIoTMQTTClient.configureEndpoint(
            AWS_IOT_CONFIG["ENDPOINT"], int(AWS_IOT_CONFIG["PORT"])
        )
        self.myAWSIoTMQTTClient.configureCredentials(
            AWS_IOT_CONFIG["ROOT_CA"],
            AWS_IOT_CONFIG["PRIVATE_KEY"],
            AWS_IOT_CONFIG["CERT_FILE"],
        )
        # AWSIoTMQTTClient connection configuration
        self.myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
        self.myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)
        self.myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)

        # set up callbacks for online and offline situation
        self.myAWSIoTMQTTClient.onOnline = self.my_online_callback
        self.myAWSIoTMQTTClient.onOffline = self.my_offline_callback

        # Persistent param
        self.CLIENT_ID = AWS_IOT_CONFIG["CLIENT_ID"]
        self.TOPIC = AWS_IOT_CONFIG["TOPIC"]
        self.MAX_ROWS = int(AWS_IOT_CONFIG["MAX_ROWS"])

        # flags
        self.online = False
        self.offline = True

    def make_batch(
        self, data_q
    ) -> List[Tuple[str, bool, bool, str, int, int]]:
        """
        Make a batch of rows to be sent via MQTT in one shot

        Args:
            data_q:     The data queue from which we get row data to make batch
        Returns:
            A list of tuple, representing a batch of data to be sent.
        Raises:
            None
        """
        batch_size: int = 0
        batch: List[Tuple[str, bool, bool, str, int, int]] = []
        while not data_q.empty() and batch_size <= self.MAX_ROWS:
            batch.append(data_q.get())
            batch_size += 1
        return batch

    def send_MQTT(self, data_q) -> bool:
        """
        Send a batch of rows via MQTT to aws iot. If sending fails, put the
        unsent data back into data_q.

        Args:
            data_q:     The data queue from which we get row to send via MQTT
        Returns:
            True if data sending succeeds, otherwise False.
        Raises:
            None
        """
        batch = self.make_batch(data_q)
        payload = json.dumps(batch)
        ret = False  # flag
        try:
            logger.debug(f"Publishing {payload}")
            ret = self.myAWSIoTMQTTClient.publish(self.TOPIC, payload, 1)
        except Exception as e:
            logger.error(f"Error in sending MQTT: {e}")
        sleep(6)  # block slightly longer than duration of time out
        if ret:
            logger.info(f"Publish payload to {self.TOPIC} successful.")
        else:  # msg sent failed.
            logger.error(f"Publish payload to {self.TOPIC} FAILED!")
            logger.info("MQTT msg not sent. Put back into data queue")
            while batch:
                data_q.put(batch.pop())  # put the unsent data back
        return ret

    def connect(self):
        """ connect shadow client and create shadow handler """
        self.myAWSIoTMQTTClient.connect()
        sleep(1)

    def disconnect(self):
        """ disconnect shadow client """
        self.myAWSIoTMQTTClient.disconnect()
        sleep(1)

    def my_online_callback(self):
        logger.info(f"{self.CLIENT_ID} ONLINE.")
        self.online = True
        self.offline = False

    def my_offline_callback(self):
        logger.info(f"{self.CLIENT_ID} OFFLINE.")
        self.offline = True
        self.online = False
