import serial
import time
from threading import Thread
import logging
import queue
import binascii


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
        self.serial = serial.Serial('port', 38400, timeout=1)
        self.data = queue.Queue()
        self.is_running = False



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def run(self):
        self.is_running = True

        while self.is_running:
            self.poll()
            data = self.serial.read(14)
            if data and len(data) == 14:
                self.data.put(binascii.hexlify(data[10:13]).decode('ascii'))

        self.__del__()



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
    def __del__(self):
        if self.serial.isOpen():
            self.serial.close()



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def poll(self):
        return True





# name
# INFO:
# ARGS:
# RETURNS:
if __name__ == "__main__":
    print('Hi')
