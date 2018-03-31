import logging
from connectors import User, IdProvider


class VCS_ID(IdProvider):

    orgname = "VCS"

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self):
        # set-up for logging of id-vcs. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.DEBUG
        self.logtitle = 'id-vcs'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def auth(self, rfid):
        try:
            return User(rfid=rfid, credits=10, nethz='default', name='Max Muster')
        except Exception as e:
            self.log.exception("auth exception: " + e)
            return False

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def report(self, rfid, slot):
        try:
            return True
        except Exception as e:
            self.log.exception("report exception: " + e)
            return False
