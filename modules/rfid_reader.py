from threading import Thread
import logging
import queue
import binascii

import Adafruit_PN532 as PN532


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
        CS = 18
        MOSI = 23
        MISO = 24
        SCLK = 25
        self.pn532 = PN532.PN532(cs=CS, sclk=SCLK, mosi=MOSI, miso=MISO)
        self.pn532.begin()
        ic, ver, rev, support = self.pn532.get_firmware_version()
        self.logger.info('Found Adafruit PN532 with firmware version: {0}.{1}'.format(ver, rev))
        self.pn532.SAM_configuration()

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def run(self):
        self.is_running = True

        while self.is_running:
            uid = self.pn532.read_passive_target()

            # break 1: check if rfid detected
            if uid is None:
                self.logger.debug('no rfid detected')
                continue
            self.logger.debug('card with UID {} found'.format(binascii.hexlify(uid)))

            # break 2: try to authenticate block for reading with default key (0xFFFFFFFFFFFF)
            if not self.pn532.mifare_classic_authenticate_block(uid, 4, self.PN532.MIFARE_CMD_AUTH_B, [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]):
                self.logger.error('failed to authenticate')
                continue
            self.logger.debug('card successfully authenticated')

            # read block data
            data = self.pn532.mifare_classic_read_block(4)

            # break 3: check if data is valid
            if data is None:
                self.logger.error('failed to read block')
                continue
            self.logger.debug('block read as {}'.format(binascii.hexlify(data[:4])))

            # push valid uid to rfid queue
            self.rfid_queue.put(binascii.hexlify(data).decode('ascii'))

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
    print('Hi')
