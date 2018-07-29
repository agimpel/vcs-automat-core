import os,sys,inspect
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir) 
import logging
import time
import os.path
import signal
from threading import Thread

from modules.telegram_bot import Telegram_Bot

# general settings
PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(PATH, "../config/")
DB = os.path.join(PATH, "../database/")


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


logger.info('start tbot thread')
tbot = Telegram_Bot()
tbot.start()


try:
    while True:
        if not tbot.isAlive():
            logger.error('tbot thread is dead')
            tbot.exit()
            if tbot.isAlive():
                tbot.join(5.0)
            sys.exit()
        time.sleep(1)


except KeyboardInterrupt:
    tbot.exit()
    if tbot.isAlive():
        tbot.join(5.0)
    sys.exit()





