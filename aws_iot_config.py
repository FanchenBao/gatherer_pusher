# config file containing credentials for connecting to aws IoT
# A random programmatic shadow client ID.
SHADOW_CLIENT = "myShadowClient"

# The unique hostname that &IoT; generated for
# this device.
HOST_NAME = "a2jj5oc6iwavb-ats.iot.us-east-2.amazonaws.com"
PORT = 8883

# The relative path to the correct root CA file for &IoT;,
# which you have already saved onto this device.
KEY_DIR = "./connect_device_package/"
ROOT_CA = KEY_DIR + "Amazon_Root_CA_1.pem"

# The relative path to your private key file that
# &IoT; generated for this device, which you
# have already saved onto this device.
PRIVATE_KEY = KEY_DIR + "99f2c83e7b-private.pem.key"

# The relative path to your certificate file that
# &IoT; generated for this device, which you
# have already saved onto this device.
CERT_FILE = KEY_DIR + "99f2c83e7b-certificate.pem.crt"

# A programmatic shadow handler name prefix.
SHADOW_HANDLER = "RPi-4-gatherer-pusher"
