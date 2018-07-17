import sys
import logging
import time
import os.path
import signal
from threading import Thread

from modules.mdb_handler import MDB_Handler
from worker import Worker

from connectors import User

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
logtitle = 'main'
logger = logging.getLogger(logtitle)
logger.setLevel(loglevel)




def dispensed_function(slot):
    return True


def credits_function(slot):
    return 10





mdbh = MDB_Handler()
mdbh.start()
mdbh.set_dispensed_callback(dispensed_function)
mdbh.set_available_callback(credits_function)


# find port with 'python -m serial.tools.list_ports'


try:
    while True:
        cmd = input('y -> enable mdbh session\n n -> disable mdbh session\n\n')
        if cmd == 'y':
            print('\n Enabled')
            mdbh.open_session = True
        elif cmd == 'n':
            print('\n Disabled')
            mdbh.open_session = False

except KeyboardInterrupt:
    mdbh.exit()
    if mdbh.isAlive():
        mdbh.join(5.0)
    sys.exit()




