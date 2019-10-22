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


# Function called when a shadow is updated
def customShadowCallback_Update(payload, responseStatus, token):
    # Display status and data from update request
    if responseStatus == "timeout":
        logger.info("Update request " + token + " time out!")

    if responseStatus == "accepted":
        payloadDict = json.loads(payload)
        logger.info("~~~~~~~~~~~~~~~~~~~~~~~")
        logger.info("Update request with token: " + token + " accepted!")
        logger.info(payloadDict)
        logger.info("~~~~~~~~~~~~~~~~~~~~~~~\n\n")

    if responseStatus == "rejected":
        logger.error("Update request " + token + " rejected!")


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
        self.myShadowClient.connect()

        # Create a programmatic representation of the shadow.
        self.myDeviceShadow = self.myShadowClient.createShadowHandlerWithName(
            aws_iot_config.SHADOW_HANDLER, True
        )

    def send_MQTT(self, insertable):
        payload = {"state": {"reported": {"rows": json.dumps(insertable)}}}
        self.myDeviceShadow.shadowUpdate(
            json.dumps(payload), customShadowCallback_Update, 5
        )
        time.sleep(1)
