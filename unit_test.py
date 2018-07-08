import sys
import logging
import time
import os.path
import signal
from threading import Thread

from modules.rfid_reader import RFID_Reader
from modules.telegram_bot import Telegram_Bot
from modules.mdb_handler_dummy import MDB_Handler
from worker import Worker

from connectors import User
from connectors.database import DB_ID
from connectors.vcs import VCS_ID
ID_PROVIDERS = (DB_ID, VCS_ID)

# general settings
PATH = os.path.abspath(os.path.dirname(__file__))
CFG = os.path.join(PATH, "/config/")
DB = os.path.join(PATH, "/database/")


# set-up of general logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s\t%(levelname)s\t[%(name)s: %(funcName)s]\t%(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    handlers=[logging.FileHandler(PATH + "/main.log"), logging.StreamHandler()])

# setting of global minimum logging level
logging.disable(logging.DEBUG)

# set-up for logging of main. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
loglevel = logging.DEBUG
logtitle = 'test'
logger = logging.getLogger(logtitle)
logger.setLevel(loglevel)



# UNIT TESTS BELOW


conn = VCS_ID()
print(conn.report('123456',3))



