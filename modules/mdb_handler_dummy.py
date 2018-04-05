import logging
from threading import Thread


class MDB_Handler(Thread):

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self):
        # set-up for logging of mdbh. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.DEBUG
        self.logtitle = 'mdbh'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        Thread.__init__(self, daemon=True)
        self.is_running = False

        self.open_session = False
        self.dispensed_callback = None
        self.available_callback = None
        self.last_amount = 0

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
    def run(self):

        self.is_running = True

        while self.is_running:
            try:
                if self.open_session:
                    self.open_session = False
                    self.last_amount = self.available_callback(0)

                    if self.last_amount:
                        self.dispensed_callback(0)
                        self.open_session = False

            except Exception as e:
                self.logger.exception("exception: {}".format(e))
                continue

        self.__del__()

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def set_dispensed_callback(self, function):
        self.dispensed_callback = function

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def set_available_callback(self, function):
        self.available_callback = function

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __del__(self):
        self.logger.info("MDB: Closing connection!")
