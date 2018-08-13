from threading import Thread
import logging
import queue
import binascii
import time
import hid



class RFID_Reader(Thread):

    numbers = {'39': 0, '30':1, '31':2, '32':3, '33':4, '34':5, '35':6, '36':7, '37':8, '38':9}

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

        # configuration of RFID Reader
        self.reader = hid.device()
        self.reader.open(0x09d8, 0x0410)
        self.reader.set_nonblocking(1)



    # run
    # INFO:     checks RFID reader for RFID tags, and if one is found, queues the corresponding UID for the worker
    # ARGS:     /
    # RETURNS:  /
    def run(self):
        self.is_running = True

        while self.is_running:
            try:
                raw_data = self.poll()
                if raw_data is not None:
                    self.logger.debug('detected rfid: '+raw_data[16:22])

                time.sleep(1)

            except Exception as e:
                self.logger.exception("exception: {}".format(e))
                continue



    def poll(self):
        data = ''
        last_input_time = time.time()
        time_delta = 2 #s

        while time.time() < last_input_time + time_delta:
            d = self.reader.read(8)
            if d and d[2] is not 0:
                last_input_time = time.time()
                if str(d[2]) in self.numbers:
                    data += str(self.numbers[str(d[2])])
        
        if data is not '':
            return data
        else:
            return None






    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def exit(self):
        self.logger.info("SHUTDOWN")
        self.is_running = False
        self.reader.close()


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













