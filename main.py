import sys
import logging
import time
import os.path
import signal
from threading import Thread

from modules.rfid_reader import RFID_Reader
from modules.telegram_bot import Telegram_Bot
from modules.mdb_handler import MDB_Handler
from worker import Worker

# general settings
PATH = os.path.abspath(os.path.dirname(__file__))
CFG = os.path.join(PATH, "/config/")
DB = os.path.join(PATH, "/database/")


class main(Thread):

    # __init__
    # INFO:     set up logging for all modules and start all threads
    # ARGS:     /
    # RETURNS:  /
    def __init__(self):

        # set-up of general logging
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s\t%(levelname)s\t[%(name)s: %(funcName)s]\t%(message)s',
                            datefmt='%Y-%m-%d %I:%M:%S',
                            handlers=[logging.FileHandler(PATH + "/main.log"), logging.StreamHandler()])

        # start services
        logging.info('starting threads')
        self.tbot = Telegram_Bot()
        self.tbot.start()
        self.rfid = RFID_Reader()
        self.rfid.start()
        self.mdbh = MDB_Handler()
        self.mdbh.start()
        self.work = Worker(self.rfid, self.mdbh, self.tbot)
        self.work.start()

        # set-up for logging of main. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.DEBUG
        self.logtitle = 'main'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

    # run
    # INFO:     scan all threads for operation and provide Exception for stopping all threads
    # ARGS:     /
    # RETURNS:  /
    def run(self):

        try:  # try-block for KeyboardInterrupt
            while True:

                if not self.tbot.isAlive():
                    self.logger.error('tbot thread is dead')

                if not self.work.isAlive():
                    self.logger.error('work thread is dead')
                    self.stop('ThreadError: work')

                if not self.mdbh.isAlive():
                    self.logger.error('mdbh thread is dead')
                    self.stop('ThreadError: mdbh')

                if not self.rfid.isAlive():
                    self.logger.error('rfid thread is dead')
                    self.stop('ThreadError: rfid')

                time.sleep(0.5)

        except KeyboardInterrupt:  # on CTRL-C, stop all threads and shut down
            self.stop('KeyboardInterrupt')

    # stop
    # INFO:     stop all threads and join them, log reason for shutdown
    # ARGS:     reason (str) -> title for the shutdown reason
    # RETURNS:  /
    def stop(self, reason='undefined'):

        self.logger.error("SHUTDOWN INITIALISED BY " + reason)

        # stop all threads manually and wait for threads to finish
        self.work.exit()
        if self.work.isAlive():
            self.work.join(5.0)
        self.mdbh.exit()
        if self.mdbh.isAlive():
            self.mdbh.join(5.0)
        self.rfid.exit()
        if self.rfid.isAlive():
            self.rfid.join(5.0)
        self.tbot.exit()
        if self.tbot.isAlive():
            self.tbot.join(5.0)

        # end the cript gracefully
        self.logger.info("SHUTDOWN FINALISED")
        sys.exit()


#
# INFO:     run script as main, attach signal handling
# ARGS:     /
# RETURNS:  /
if __name__ == "__main__":

    print("Hello World!")

    # start main thread
    main = main()
    main.run()

    # attach SIGTERM handling
    signal.signal(signal.SIGTERM, main.stop('SIGTERM'))
