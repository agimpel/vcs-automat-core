import os
import configparser
from threading import Thread
import logging
import queue
import binascii
import time
import evdev
import asyncio

from modules import CFG, DB

# Name of the RFID reader. Find via devices=[evdev.InputDevice(path) for path in evdev.list_devices()]; for device in devices: print(device.path, device.name, device.phys)
RFID_USB_NAME = 'OEM RFID Device (Keyboard)' 



class RFID_Reader(Thread):

    # __init__
    # INFO:     Sets up logging and basic variables of this class.
    # ARGS:     /
    # RETURNS:  /
    def __init__(self):
        # set-up for logging of rfid. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.INFO
        self.logtitle = 'rfid'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        Thread.__init__(self, daemon=True)
        self.rfid_queue = queue.Queue()
        self.is_running = False

        # read stamp for rfid validation from config file
        self.read_cfg(os.path.join(CFG, "rfid.cfg"))

        # set up RFID device by identification of its name
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        if RFID_USB_NAME not in [device.name for device in devices]:
            self.logger.error('RFID reader not found in devices. Try finding it with sudo and set up its permissions via udev rule')
            self.reader = None
            return
        
        path = devices[[device.name for device in devices].index(RFID_USB_NAME)].path
        self.logger.info('Found RFID reader at '+path)
        try:
            self.reader = evdev.InputDevice(path)
        except Exception as e:
            self.logger.error('Could not open RFID reader.')
            self.reader = None
            return

        # get exclusive read on device via EVIOCGRAB
        self.reader.grab()
        self.flush()
        self.logger.info('Successfully connected, grabbed and flushed the RFID reader. Listening.')

    # run
    # INFO:     Main thread of this class. Continuosly checks RFID reader for RFID tags, and if one is found, queues the corresponding UID for the main class.
    # ARGS:     /
    # RETURNS:  /
    def run(self):
        self.is_running = True

        while self.is_running:
            try:
                # read the rfid reader and validate the raw data
                raw_data = self.poll()
                self.logger.debug('Processing raw data from rfid reader.')
                rfid = self.validate(raw_data)
                if rfid is not False:
                    # if a valid rfid was found, queue it in the main class
                    self.logger.debug('detected rfid: '+str(rfid))
                    self.rfid_queue.put(rfid)

                # sleep to prevent hogging resources
                time.sleep(0.1)

            except Exception as e:
                self.logger.exception("exception: {}".format(e))
                continue

    # poll
    # INFO:     Reads the RFID reader which is connected as a keyboard. Due to it being a keyboard, it registers all events as keystrokes, which a filtered and processed with the evdev package.
    # ARGS:     /
    # RETURNS:  preprocessed data string of the RFID reader output
    def poll(self):
        # flush all input prior to reading
        self.flush()
        self.logger.debug('Started polling ...')
        data = ''
        # continuosly read the RFID reader's keystrokes
        for event in self.reader.read_loop():
            # only register keystrokes, and filter out Shift, append to data string
            if event.type is evdev.ecodes.EV_KEY and event.value is 1 and event.code is not evdev.ecodes.ecodes['KEY_LEFTSHIFT']:
                data += evdev.ecodes.keys[event.code]
            # the RFID reader ends its output with the "\nEND\n", even if the RFID tag was removed prematurely. Thus this signal is used for termination of the read loop. Then all newlines and spaces are replaced by their real equivalents, in addition to removing all KEY_ prefixes to convert into real string.
            if data.endswith('KEY_ENTERKEY_EKEY_NKEY_DKEY_ENTER'):
                self.logger.debug('Found end of reader output.')
                data = data.replace('KEY_ENTER', '\n')
                data = data.replace('KEY_SPACE', ' ')
                data = data.replace('KEY_', '')
                return data

    # flush
    # INFO:     As long as there is data on the serial bus, discard it. Used to completely wipe the input.
    # ARGS:     /
    # RETURNS:  /
    def flush(self):
        while self.reader.read_one() != None:
            self.logger.debug('Flushed.')
            pass

    # validate
    # INFO:     Validates that the raw data of the RFID reader actually corresponds to a valid student id card. This uses the manufacturer name and a special stamp which is unique for the organisation. The stamp itself and its position within the reader output are obfuscated, as they are not public. The UID immediately follows the stamp and has six characters.
    # ARGS:     raw_input (string) -> preprocessed data string of the RFID reader output
    # RETURNS:  the UID of the RFID tag as string if RFID is valid, False otherwise
    def validate(self, raw_input):
        if len(raw_input) < 50:
            self.logger.info('Input was too short.')
            return False
        if raw_input[0:5] != 'LEGIC':
            self.logger.info('RFID is not of type LEGIC, got '+str(raw_input[0:5]))
            return False
        if raw_input[self.stamp_index:self.stamp_index+len(self.stamp)] != self.stamp:
            self.logger.info('RFID stamp was not correct, got '+str(raw_input[self.stamp_index:self.stamp_index+len(self.stamp)]))
            return False

        self.logger.debug('RFID was valid.')
        return raw_input[self.stamp_index+len(self.stamp):self.stamp_index+len(self.stamp)+6]

    # read_cfg
    # INFO:     Reads this class' config file.
    # ARGS:     cfg_path (string) -> path to the config file
    # RETURNS:  /
    def read_cfg(self, cfg_path):
        config = configparser.SafeConfigParser()
        config.read(cfg_path)
        self.stamp = str(config['rfid']['stamp'])
        self.stamp_index = int(config['rfid']['index'])

    # exit
    # INFO:     Shuts down this thread.
    # ARGS:     /
    # RETURNS:  /
    def exit(self):
        self.logger.info("SHUTDOWN")
        self.is_running = False
        self.reader.ungrab()
        self.reader.close()


# FOR TESTING ONLY
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
