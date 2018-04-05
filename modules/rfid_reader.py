from threading import Thread
import logging
import queue
import binascii
import time

import modules.PN532 as PN532


class RFID_Reader(Thread):

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self):
        # set-up for logging of rfid. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.DEBUG
        self.logtitle = 'rfid'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        Thread.__init__(self, daemon=True)
        self.rfid_queue = queue.Queue()
        self.is_running = False

        # configuration of Adafruit PN532 for RaspberryPi
        self.pn532 = PN532.PN532("/dev/ttyS0")
        self.pn532.begin()
        ic, ver, rev, support = self.pn532.get_firmware_version()
        self.logger.info('Found Adafruit PN532 with firmware version: {}.{}'.format(ver, rev))
        self.pn532.SAM_configuration()

    # run
    # INFO:     checks RFID reader for RFID tags, and if one is found, queues the corresponding UID for the worker
    # ARGS:     /
    # RETURNS:  /
    def run(self):
        self.is_running = True

        while self.is_running:
            try:
                uid = self.pn532.read_passive_target()

                # break 1: check if rfid detected
                if uid is None:
                    self.logger.debug('no rfid detected')
                    continue
                self.logger.debug('card with UID {} found'.format(binascii.hexlify(uid).decode('ascii')))

                # push uid to rfid queue
                self.rfid_queue.put(binascii.hexlify(uid).decode('ascii'))

                time.sleep(5)

            except Exception as e:
                self.logger.exception("exception: {}".format(e))
                continue

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
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s\t%(levelname)s\t[%(name)s: %(funcName)s]\t%(message)s',
                        datefmt='%Y-%m-%d %I:%M:%S')
    rfid = RFID_Reader()
    rfid.start()

    try:  # try-block for KeyboardInterrupt
        while True:
            time.sleep(0.5)

    except KeyboardInterrupt:  # on CTRL-C, stop all threads and shut down
        rfid.exit()
        if rfid.isAlive():
            rfid.join(5.0)
