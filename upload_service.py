from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient
import aws_iot_config
import json
import time
import logging
import logging.config
import yaml

# set up logger
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f.read())
    logging.config.dictConfig(config)
logger = logging.getLogger("AWSIoTPythonSDK.core")


class UploadService:
    """ A class to handle uploading probe request data via MQTT to aws IoT.
    """

    def __init__(self):
        # Create, configure, and connect a shadow client.
        self.myShadowClient = AWSIoTMQTTShadowClient(
            aws_iot_config.SHADOW_CLIENT
        )
        self.myShadowClient.configureEndpoint(
            aws_iot_config.HOST_NAME, aws_iot_config.PORT
        )
        self.myShadowClient.configureCredentials(
            aws_iot_config.ROOT_CA,
            aws_iot_config.PRIVATE_KEY,
            aws_iot_config.CERT_FILE,
        )
        # AWSIoTMQTTShadowClient connection configuration
        self.myShadowClient.configureAutoReconnectBackoffTime(1, 32, 20)
        self.myShadowClient.configureConnectDisconnectTimeout(10)
        self.myShadowClient.configureMQTTOperationTimeout(5)
        self.myDeviceShadow = None

        # set up callbacks for online and offline situation
        self.myShadowClient.onOnline = self.my_online_callback
        self.myShadowClient.onOffline = self.my_offline_callback
        self.connect()

        # flags
        self.msg_sent = False
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
        payload = {"state": {"reported": {"rows": json.dumps(insertable)}}}
        try:
            self.myDeviceShadow.shadowUpdate(
                json.dumps(payload), self.customShadowCallback_Update, 5
            )
        except Exception as e:
            logger.error(f"Error in sending MQTT: {e}")
        time.sleep(1)

    def connect(self):
        """ connect shadow client and create shadow handler """
        self.myShadowClient.connect()
        # Create a programmatic representation of the shadow.
        self.myDeviceShadow = self.myShadowClient.createShadowHandlerWithName(
            aws_iot_config.SHADOW_HANDLER, True
        )

    def disconnect(self):
        """ disconnect shadow client """
        self.myShadowClient.disconnect()

    # callbacks
    # Function called when a shadow is updated
    def customShadowCallback_Update(self, payload, responseStatus, token):
        # Display status and data from update request
        if responseStatus == "timeout":
            logger.info("Update request " + token + " time out!")
            self.msg_sent = False

        if responseStatus == "accepted":
            payloadDict = json.loads(payload)
            logger.info("~~~~~~~~~~~~~~~~~~~~~~~")
            logger.info("Update request with token: " + token + " accepted!")
            logger.info(payloadDict)
            logger.info("~~~~~~~~~~~~~~~~~~~~~~~\n\n")
            self.msg_sent = True

        if responseStatus == "rejected":
            logger.error("Update request " + token + " rejected!")
            self.msg_sent = False

    def my_online_callback(self):
        logger.info(f"{aws_iot_config.SHADOW_CLIENT} ONLINE.")
        self.online = True
        self.offline = False

    def my_offline_callback(self):
        logger.info(f"{aws_iot_config.SHADOW_CLIENT} OFFLINE.")
        self.offline = True
        self.online = False
