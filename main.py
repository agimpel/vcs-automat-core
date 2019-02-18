import sys
import logging
import time
import os.path
import signal
from threading import Thread
import queue

from modules.rfid_reader import RFID_Reader
from modules.telegram_bot import Telegram_Bot
from modules.mdb_handler import MDB_Handler

from connectors import User
from connectors.database import DB_ID
from connectors.vcs import VCS_ID
ID_PROVIDERS = (VCS_ID,)

# general settings
PATH = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(PATH, "/config/")
DB = os.path.join(PATH, "/database/")


class Main(Thread):

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self):

                # set-up of general logging
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s\t%(levelname)s\t[%(name)s: %(funcName)s]\t%(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            handlers=[logging.FileHandler(PATH + "/main.log"), logging.StreamHandler()])

        # setting of global minimum logging level
        logging.disable(logging.NOTSET)

        # start services
        logging.info('starting threads')
        self.tbot = Telegram_Bot()
        self.tbot.start()
        self.rfid = RFID_Reader()
        self.rfid.start()
        self.mdbh = MDB_Handler()
        self.mdbh.start()


        # set-up for logging of work. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.INFO
        self.logtitle = 'main'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        Thread.__init__(self, daemon=True)
        self.is_running = False

        self.vending_queue = queue.Queue()

        self.current_uid = 0
        self.current_credits = 0
        self.current_user = User()
        self.current_org = 'undefined'
        self.mdbh.set_dispensed_callback(self.queue_vending)
        self.mdbh.set_available_callback(self.credits_available)

        # initialize ID providers
        self.providers = {}
        for connector in ID_PROVIDERS:
            self.providers[connector.orgname] = connector()

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def run(self):
        self.is_running = True

        try:
            while self.is_running:

                # first queue: vending
                if not self.vending_queue.empty():
                    self.logger.debug('vending queue non-empty, processing queue')
                    try:
                        (slot_id, rfid, org) = self.vending_queue.get()
                        if self.providers[org].report(rfid, slot_id):
                            self.logger.debug("report of vending for {} successful".format(org))
                        else:
                            self.logger.error("report of vending for {} failed".format(org))

                    except Exception as e:
                        self.logger.exception("exception: {}".format(e))
                        continue

                # second queue: RFID reader
                if not self.rfid.rfid_queue.empty():
                    self.logger.debug('rfid queue non-empty, processing queue')
                    try:
                        self.current_uid = self.rfid.rfid_queue.get()
                        # look up the rfid as id: False if unknown, array of (credits, user, org) if rfid is known. If rfid is known, enable vending
                        id = self.uid_lookup(self.current_uid)
                        if id is not False:
                            (self.current_credits, self.current_user, self.current_org) = id
                            self.logger.info("rfid {} was found in {} with {} credits".format(self.current_uid, self.current_org, self.current_credits))
                            if self.current_credits > 0:
                                self.mdbh.open_session = True
                            else:
                                self.mdbh.display_queue.put({'top': 'Kein Guthaben', 'bot': ':\'(', 'duration': 3})
                                (self.current_credits, self.current_user, self.current_org) = (0, User(), 'undefined')
                        else:
                            self.mdbh.display_queue.put({'top': 'Legi/Benutzer', 'bot': 'unbekannt', 'duration': 3})
                            self.logger.error("rfid {} was unknown, dismissing".format(self.current_uid))
                            (self.current_credits, self.current_user, self.current_org) = (0, User(), 'undefined')
                            self.mdbh.open_session = False

                    except Exception as e:
                        self.logger.exception("exception: {}".format(e))
                        continue

                # sleep
                time.sleep(0.2)

        except KeyboardInterrupt:  # on CTRL-C, stop all threads and shut down
            self.stop('KeyboardInterrupt')


    # stop
    # INFO:     stop all threads and join them, log reason for shutdown
    # ARGS:     reason (str) -> title for the shutdown reason
    # RETURNS:  /
    def stop(self, reason='undefined'):

        self.logger.error("SHUTDOWN INITIALISED BY " + reason)

        # stop all threads manually and wait for threads to finish
        self.is_running = False
        self.mdbh.exit()
        if self.mdbh.isAlive():
            self.mdbh.join(5.0)
        self.rfid.exit()
        if self.rfid.isAlive():
            self.rfid.join(5.0)
        self.tbot.exit()
        if self.tbot.isAlive():
            self.tbot.join(5.0)

        # end the script gracefully
        self.logger.info("SHUTDOWN FINALISED")
        sys.exit()

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def credits_available(self, slot_id):
        if self.current_credits > 0:
            return self.current_credits
        return 0

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def queue_vending(self, slot_id):
        self.current_credits -= 1
        self.vending_queue.put((slot_id, self.current_uid, self.current_org))
        self.tbot.update_fillstatus_callback(slot_id)

    # uid_lookup
    # INFO:     looks up 'rfid' from RFID reader in all identification providers and returns info on user, available credits and the authenticating organisation
    #           if multiple identification providers recognize 'rfid', the match with the highest amount of credits is chosen and returned
    #           if no identification provides recognize 'rfid', False is returned
    # ARGS:     rfid (int) -> RFID to be identified as read by RFID reader
    # RETURNS:  Array (int credits, User user, str org) with relevant info on the user if rfid is known, False otherwise
    def uid_lookup(self, rfid):
        self.logger.debug("looking up RFID {}".format(rfid))
        credits = None
        user = None
        org = None
        best_result = (credits, user, org)

        # if there already is a vending in progress, dismiss
        if not self.vending_queue.empty():
            self.logger.error('vending still in progress, dismissing rfid authentication')
            return False

        for id_provider in list(self.providers.values()):
            # try to authenticate user with this id provider
            user = id_provider.auth(rfid)
            # if a valid user is found, update best_result if this org increases the user's available credits
            if user is not None:
                org = id_provider.orgname
                credits = user.credits
                self.logger.info('rfid %s matched from %s with %d credits', rfid, org, credits)
                if best_result[0] is None or best_result[0] < credits:
                    best_result = (credits, user, org)

        # return False if the user is unknown or the result with the highest number of available credits if user is known
        if best_result[1] is None:
            self.logger.error('rfid %s had no match', rfid)
            return False
        else:
            self.logger.info('rfid %s matched from %s with %d credits as best result', best_result[1].rfid, best_result[2], best_result[0])
            return best_result



#
# INFO:     run script as main, attach signal handling
# ARGS:     /
# RETURNS:  /
if __name__ == "__main__":

    # start main thread
    main = Main()
    main.run()

    # attach SIGTERM handling
    signal.signal(signal.SIGTERM, main.stop('SIGTERM'))
