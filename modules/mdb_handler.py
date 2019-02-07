import binascii
import sys
import logging
import serial
from threading import Thread
import time
import struct


class MDB_Handler(Thread):

    # Timeout in seconds
    TIMEOUT = 12

    # MDB2PC Constants
    MDB2PC_NAK = b'\x15'
    MDB2PC_ACK = b'\x06'
    MDB2PC_FRAME_START = b'\x02'
    MDB2PC_FRAME_BEGIN = b'\x02\x00'
    MDB2PC_FRAME_STOP = b'\x10\x03'

    # MDB Constants
    MDB_ACK = b''
    MDB_JUST_RESET = b'\x00'
    MDB_POLL = b'\x12'
    MDB_RESET = b'\x10\x10'
    MDB_READER_ENABLE = b'\x14\x01'
    MDB_OUT_OF_SEQUENCE = b'\x0B'
    MDB_READER_CONFIG_RESPONSE = b'\x01\x01\x02\xF4\x01\x02\x02\x00'
    MDB_EXT_FEATURES_RESPONSE = b'\x09\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    MDB_VEND_REQUEST = b'\x13\x00'
    MDB_VEND_SUCCESFUL = b'\x13\x02'
    MDB_VEND_CANCEL = b'\x13\x01'
    MDB_SESSION_COMPLETE = b'\x13\x04'
    MDB_OPEN_SESSION = b'\x03\x07\xd0'
    MDB_CANCEL_REQUEST = b'\x04'
    MDB_END_SESSION = b'\x07'
    MDB_VEND_DENIED = b'\x06'
    MDB_VEND_APPROVED = b'\x05\x00\x02'

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __init__(self):
        # set-up for logging of mdbh. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.INFO
        self.logtitle = 'mdbh'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        Thread.__init__(self, daemon=True)
        self.is_running = False

        self.ser = serial.Serial('/dev/ttyS0', 115200, timeout=0.1) # find port with 'python -m serial.tools.list_ports'
        self.open_session = False
        self.state = "RESET"
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
            frame = self.poll_data()
            if frame is not None:
                self.handle_data(frame)

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
    def poll_data(self):
        s = self.ser.read(1)
        if s == self.MDB2PC_NAK:
            self.logger.debug("MDB2PC: [IN] NAK")
        if s == self.MDB2PC_ACK:
            self.logger.debug("MDB2PC: [IN] ACK")
        if s == b'\x02':
            s = s + self.ser.read(10)
            start = s.find(self.MDB2PC_FRAME_BEGIN) + 2
            end = s.find(self.MDB2PC_FRAME_STOP, start)
            data = s[start:end]
            self.logger.debug("MDB2PC: [IN] MDB Frame " + str(binascii.hexlify(data)))
            self.ser.write(self.MDB2PC_ACK)
            self.logger.debug("MDB2PC: [OUT] ACK")
            sys.stdout.flush()
            return data
        return None

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def send_data(self, data):
        self.ser.write(b'\x02\x00' + data + b'\x10\x03')

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def handle_data(self, data):
        if self.state == "RESET":
            self.logger.debug("STATE: RESET")
            if data == self.MDB_POLL:  # POLL
                self.logger.debug("MDB: [IN] Poll")
                self.send_data(self.MDB_JUST_RESET)
                self.state = "DISABLED"
            elif data == self.MDB_RESET:  # RESET
                self.logger.info("MDB: [IN] Reset")
                self.send_data(self.MDB_ACK)
            else:
                self.logger.info("MDB: [IN] Unhandled Frame " + str(binascii.hexlify(data)))
                self.logger.info("MDB: [IN] %s" % self.state)
                self.send_data(self.MDB_OUT_OF_SEQUENCE)

        elif self.state == "DISABLED":
            self.logger.info("STATE: DISABLED")
            if data == self.MDB_POLL:  # POLL
                self.logger.debug("MDB: [IN] Poll")
                self.send_data(self.MDB_ACK)
            elif data == self.MDB_RESET:  # RESET
                self.logger.info("MDB: [IN] Reset")
                self.send_data(self.MDB_ACK)
                self.state = "RESET"
            elif data == b'\x11\x00\x03\x10\x10\x02\x01':  # SETUP CONFIG
                self.logger.debug("MDB: [IN] Setup Config")
                self.send_data(self.MDB_READER_CONFIG_RESPONSE)
            elif data == b'\x11\x01\x03\xe8\x00\x05':
                self.logger.debug("MDB: [IN] MinMax Prices")
                self.send_data(self.MDB_ACK)
            elif data == self.MDB_READER_ENABLE:
                self.logger.info("MDB: [IN] Reader Enable")
                self.send_data(self.MDB_ACK)
                self.state = "ENABLED"
            elif data == b'\x17\x00SIE000':
                self.logger.debug("MDB: [IN] Extended Features")
                self.send_data(self.MDB_EXT_FEATURES_RESPONSE)
            else:
                self.logger.info("MDB: [IN] Unhandled Frame " + str(binascii.hexlify(data)))
                self.logger.info("MDB: [IN] %s" % self.state)
                self.send_data(self.MDB_OUT_OF_SEQUENCE)

        elif self.state == "ENABLED":
            self.logger.debug("STATE: ENABLED")
            if data == self.MDB_POLL:  # POLL
                self.logger.debug("MDB: [IN] Poll")
                if self.open_session:
                    self.timer = time.time()
                    self.send_data(self.MDB_OPEN_SESSION)
                    self.state = "DISPLAY SESSION"
                    self.open_session = False
                    self.last_amount = self.available_callback(0)
                else:
                    self.send_data(self.MDB_ACK)

            elif data == self.MDB_READER_ENABLE:
                self.logger.debug("MDB: [IN] Reader Enable")
                self.send_data(self.MDB_ACK)
            elif data == self.MDB_RESET:  # RESET
                self.logger.info("MDB: [IN] Reset")
                self.send_data(self.MDB_ACK)
                self.state = "RESET"
            else:
                self.logger.info("MDB: [IN] Unhandled Frame " + str(binascii.hexlify(data)))
                self.logger.info("MDB: [IN] %s" % self.state)
                self.send_data(self.MDB_OUT_OF_SEQUENCE)

        elif self.state == "SESSION":
            self.logger.debug("STATE: SESSION")
            if data == self.MDB_POLL:  # POLL
                self.logger.debug("MDB: [IN] Poll")
                if time.time() - self.timer > self.TIMEOUT:
                    self.state = "SESSION END"
                else:
                    self.send_data(self.MDB_ACK)
            elif data[0:2] == self.MDB_VEND_REQUEST:
                self.logger.info("MDB: [IN] Vend Request")
                self.slot = struct.unpack('>H', data[4:6])[0]
                self.last_amount = self.available_callback(self.slot)
                self.logger.info('self last amount %d', self.last_amount)
                if self.last_amount:
                    self.logger.info("MDB: [LOGIC] Request Approved, " + str(self.last_amount - 1) + " credits left")
                    self.send_data(self.MDB_VEND_APPROVED)
                else:
                    self.logger.info("MDB: [LOGIC] Request Denied")
                    self.send_data(self.MDB_VEND_DENIED)

            elif data[0:2] == self.MDB_VEND_SUCCESFUL:
                self.logger.info("MDB: [IN] Vend Success")
                self.dispensed_callback(self.slot)
                self.send_data(self.MDB_CANCEL_REQUEST)
                self.state = "SESSION END"
            elif data[0:2] == self.MDB_VEND_CANCEL:
                # User put in coins
                self.logger.info("MDB: [IN] Vend Cancel")
                self.send_data(self.MDB_VEND_DENIED)
                self.state = "VEND CANCELED"
            elif data == self.MDB_RESET:  # RESET
                self.logger.info("MDB: [IN] Reset")
                self.send_data(self.MDB_ACK)
                self.state = "RESET"
            elif data == self.MDB_SESSION_COMPLETE:
                self.logger.info("MDB: [IN] Session Complete")
                self.send_data(self.MDB_ACK)
                self.state = "SESSION END"
            else:
                self.logger.info("MDB: [IN] Unhandled Frame " + str(binascii.hexlify(data)))
                self.logger.info("MDB: [IN] %s" % self.state)
                self.send_data(self.MDB_OUT_OF_SEQUENCE)

        elif self.state == "SESSION END":
            self.logger.debug("STATE: SESSION END")
            if data == self.MDB_POLL:
                self.logger.debug("MDB: [IN] Poll")
                self.send_data(self.MDB_END_SESSION)
                self.state = "DISPLAY END SESSION"
            else:
                self.logger.info("MDB: [IN] Unhandled Frame " + str(binascii.hexlify(data)))
                self.logger.info("MDB: [IN] %s" % self.state)
                self.send_data(self.MDB_OUT_OF_SEQUENCE)

        elif self.state == "DISPLAY SESSION":
            self.logger.debug("STATE: DISPLAY")
            if data == self.MDB_POLL:  # POLL
                self.logger.debug("MDB: [IN] Poll")
                self.send_data(b'\x02\x3C      VCS         ' + str(self.last_amount).encode('ascii') + b' Freibier    ')
                self.state = "SESSION"
            else:
                self.logger.info("MDB: [IN] Unhandled Frame " + str(binascii.hexlify(data)))
                self.logger.info("MDB: [IN] %s" % self.state)
                self.send_data(self.MDB_OUT_OF_SEQUENCE)

        elif self.state == "DISPLAY END SESSION":
            self.logger.debug("STATE: DISPLAY")
            if data == self.MDB_POLL:  # POLL
                self.logger.debug("MDB: [IN] Poll")
                self.send_data(b'\x02\x0A      VCS              <3        ')
                self.state = "ENABLED"
            else:
                self.logger.info("MDB: [IN] Unhandled Frame " + str(binascii.hexlify(data)))
                self.logger.info("MDB: [IN] %s" % self.state)
                self.send_data(self.MDB_OUT_OF_SEQUENCE)

        elif self.state == "VEND CANCELED":
            self.logger.debug("STATE: VEND CANCELED")
            if data == self.MDB_POLL:
                self.logger.debug("MDB: [IN] Poll")
                self.send_data(b'\x06')
                self.state = "SESSION"
            else:
                self.logger.info("MDB: [IN] Unhandled Frame " + str(binascii.hexlify(data)))
                self.logger.info("MDB: [IN] %s" % self.state)
                self.send_data(self.MDB_OUT_OF_SEQUENCE)

    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __del__(self):
        # send session_complete after poll
        self.logger.debug("MDB: Closing connection!")
        frame = self.poll_data()
        while frame is None:
            frame = self.poll_data()
        if frame == self.MDB_POLL:
            self.logger.debug("MDB: [IN] Poll")
            self.send_data(self.MDB_JUST_RESET)
            self.logger.debug("MDB: [LOGIC] Just reset")
        else:
            self.logger.info("MDB: [IN] Unhandled Frame {}".format(binascii.hexlify(frame)))
            self.logger.info("MDB: [IN] %s" % self.state)
            self.send_data(self.MDB_JUST_RESET)
            self.logger.debug("MDB: [LOGIC] Just reset")

        if self.ser.isOpen():
            self.ser.close()
