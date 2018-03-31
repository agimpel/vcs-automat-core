import logging
import time
import queue
from threading import Thread


from connectors import User
from connectors.database import DB_ID
from connectors.vcs import VCS_ID
ID_PROVIDERS = (DB_ID, VCS_ID)


class Worker(Thread):

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self, rfid, mdbh, tbot):
        # set-up for logging of work. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.DEBUG
        self.logtitle = 'work'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        Thread.__init__(self, daemon=True)
        self.is_running = False

        # assign all instances to modules as initialised by main
        self.rfid = rfid
        self.mdbh = mdbh
        self.tbot = tbot

        self.vending_queue = queue.Queue()

        self.current_uid = 0
        self.current_credits = 0
        self.current_user = User()
        self.current_org = 'undefined'
        self.mdbh.set_ack_dispensed_callback(self.ack_dispensed_beer)
        self.mdbh.set_beer_is_available_callback(self.beer_is_available)

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
            elif not self.rfid.rfid_queue.empty():
                self.logger.debug('rfid queue non-empty, processing queue')
                try:
                    self.current_uid = self.rfid.rfid_queue.get()
                    # look up the rfid as id: False if unknown, array of (credits, user, org) if rfid is known. If rfid is known, enable vending
                    id = self.uid_lookup(self.current_uid)
                    if id is not False:
                        self.logger.debug("rfid {} was found in {} for user {} with {} credits".format(self.current_uid, self.current_org, self.current_user.name, self.current_credits))
                        (self.current_credits, self.current_user, self.current_org) = id
                        self.mdbh.open_session = True
                    else:
                        self.logger.error("rfid {} was unknown, dismissing".format(self.current_uid))
                        (self.current_credits, self.current_user, self.current_org) = (0, User(), 'undefined')
                        self.mdbh.open_session = False

                except Exception as e:
                    self.logger.exception("exception: {}".format(e))
                    continue

            # sleep
            time.sleep(0.2)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def exit(self):
        self.logger.info("SHUTDOWN")
        self.is_running = False

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def beer_is_available(self, slot_id):
        if self.current_credits > 0:
            return self.current_credits
        return 0

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def ack_dispensed_beer(self, slot):
        self.current_credits -= 1
        self.dispensed_beer.put((slot, self.current_uid, self.org))
        if self.current_credits > 0:
            self.mdb.open_session = True

    # uid_lookup
    # INFO:     looks up 'rfid' from RFID reader in all identification providers and returns info on user, available credits and the authenticating organisation
    #           if multiple identification providers recognize 'rfid', the match with the highest amount of credits is chosen and returned
    #           if no identification provides recognize 'rfid', False is returned
    # ARGS:     rfid (int) -> RFID to be identified as read by RFID reader
    # RETURNS:  Array (int credits, User user, str org) with relevant info on the user if rfid is known, False otherwise
    def uid_lookup(self, rfid):
        credits = 0
        user = None
        org = None
        best_result = (credits, user, org)

        # if there already is a vending in progress, dismiss
        if not self.dispensed_beer.empty():
            self.logger.error('vending still in progress, dismissing rfid authentication')
            return False

        for id_provider in list(self.providers.values()):
            # try to authenticate user with this id provider
            user = id_provider.auth(rfid)
            # if a valid user is found, update best_result if this org increases the user's available credits
            if user is not None:
                org = id_provider.orgname
                credits = user.credits
                if best_result[0] < credits:
                    best_result = (credits, user, org)

        # return False if the user is unknown or the result with the highest number of available credits if user is known
        if user is None:
            self.logger.error('rfid %s had no match', user.rfid)
            return False
        else:
            self.logger.info('rfid %s matched from %s with %d credits', user.rfid, org, credits)
            return best_result


# name
# INFO:
# ARGS:
# RETURNS:
if __name__ == "__main__":
    print('Hi')
