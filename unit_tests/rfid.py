import os,sys,inspect
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir) 
import logging
import time
import os.path
import signal
from threading import Thread

from modules.rfid_reader import RFID_Reader

# general settings
PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(PATH, "../config/")
DB = os.path.join(PATH, "../database/")


# set-up of general logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s\t%(levelname)s\t[%(name)s: %(funcName)s]\t%(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    handlers=[logging.FileHandler(PATH + "/main.log"), logging.StreamHandler()])

# set-up for logging of main. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
loglevel = logging.DEBUG
logtitle = 'main'
logger = logging.getLogger(logtitle)
logger.setLevel(loglevel)


logger.info('start rfid thread')
rfid = RFID_Reader()
rfid.start()

try:  # try-block for KeyboardInterrupt
    while True:
        time.sleep(0.5)

except KeyboardInterrupt:  # on CTRL-C, stop all threads and shut down
    rfid.exit()
    if rfid.isAlive():
        rfid.join(5.0)