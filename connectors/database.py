import logging
from connectors import User, IdProvider


class DB_ID(IdProvider):

    orgname = "DB"

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self):
        # set-up for logging of id-db. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.DEBUG
        self.logtitle = 'id-db'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def auth(self, rfid):
        return False

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report(self, rfid, slot):
        try:
            return True
        except Exception as e:
            self.logger.exception("report exception: " + e)
            return False
