from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import json
from time import sleep
import logging
import logging.config
import yaml

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
            AWS_IOT_CONFIG["ENDPOINT"], AWS_IOT_CONFIG["PORT"]
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

        # flags
        self.online = False
        self.offline = True

    def send_MQTT(self, insertable):
        """
        send serialized `insertable`, which is a List of Tuples to aws
        iot via MQTT.

        Args:
            insertable:     A list of tuples, with each tuple representing a row
        Returns:
            None
        Raises:
            None
        """
        ret = False  # flag
        payload = json.dumps(insertable)
        try:
            logger.debug(f"Publishing {payload}")
            ret = self.myAWSIoTMQTTClient.publish(self.TOPIC, payload, 1)
        except Exception as e:
            logger.error(f"Error in sending MQTT: {e}")
        sleep(6)  # block slightly longer than duration of time out
        if ret:
            logger.info(f"Publish payload to {self.TOPIC} successful.")
        else:
            logger.error(f"Publish payload to {self.TOPIC} FAILED!")
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
