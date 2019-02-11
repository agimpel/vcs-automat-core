import binascii
import sys
import logging
import serial
from threading import Thread
import time
import struct
import queue


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
    MDB_READER_SETUP_CONFIG = b'\x11\x00\x03\x10\x10\x02\x01'
    MDB_READER_CONFIG_RESPONSE = b'\x01\x01\x02\xF4\x01\x02\x02\x00'
    MDB_READER_MINMAX_PRICES = b'\x11\x01\x03\xe8\x00\x05'
    MBD_READER_EXT_FEATURES = b'\x17\x00SIE000'
    MDB_EXT_FEATURES_RESPONSE = b'\x09\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    MDB_VEND_REQUEST = b'\x13\x00'
    MDB_VEND_SUCCESFUL = b'\x13\x02'
    MDB_VEND_CANCEL = b'\x13\x01'
    MDB_SESSION_COMPLETE = b'\x13\x04'
    MDB_DISPLAY_REQUEST = b'\x02'
    MDB_OPEN_SESSION = b'\x03\xff\xff'
    MDB_CANCEL_REQUEST = b'\x04'
    MDB_END_SESSION = b'\x07'
    MDB_VEND_DENIED = b'\x06'
    MDB_VEND_APPROVED = b'\x05\xff\xff'

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
        self.substate = None
        self.display_queue = queue.Queue()
        self.dispensed_callback = None
        self.available_callback = None
        self.last_amount = 0

        self.default_display = {'top': 'VCS-Bierautomat', 'bottom': 'Legi einscannen', 'duration': 5}



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
            data = self.poll_data()

            if data is not None:

                if data == self.MDB_POLL and self.display_queue.empty() is False:
                    self.send_display_order(self.display_queue.get())

                elif self.state == "RESET":
                    self.handle_data_reset(data)

                elif self.state == "DISABLED":
                    self.handle_data_disabled(data)

                elif self.state == "ENABLED":
                    self.handle_data_enabled(data)

                elif self.state == "SESSION":
                    self.handle_data_session(data)

                else:
                    self.logger.error("Encountered unexpected state: " + str(self.state))
                    self.send_data(self.MDB_JUST_RESET)
                    self.logger.debug("OUT: Just reset")

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
        if s == self.MDB2PC_FRAME_START:
            s = s + self.ser.read(10)
            start = s.find(self.MDB2PC_FRAME_BEGIN) + 2
            end = s.find(self.MDB2PC_FRAME_STOP, start)
            data = s[start:end]
            self.logger.debug("MDB2PC: [IN] MDB Frame " + str(binascii.hexlify(data)))
            self.ser.write(self.MDB2PC_ACK)
            self.logger.debug("MDB2PC: [OUT] ACK")
            return data
        return None



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def send_data(self, data):
        self.ser.write(self.MDB2PC_FRAME_BEGIN + data + self.MDB2PC_FRAME_STOP)





    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def handle_data_reset(self, data):
        self.logger.debug("STATE: RESET")

        if data == self.MDB_POLL:  # POLL
            self.logger.debug("IN: Poll")
            self.send_data(self.MDB_JUST_RESET)
            self.logger.debug('OUT: Just Reset')
            self.state = "DISABLED"
            self.logger.info("PROCEED TO: DISABLED")

        elif data == self.MDB_RESET:  # RESET
            self.logger.debug("IN: Reset")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")

        else:
            self.logger.info("IN: Unhandled Frame " + str(binascii.hexlify(data)))
            self.send_data(self.MDB_OUT_OF_SEQUENCE)
            self.logger.debug("OUT: Out Of Sequence")



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def handle_data_disabled(self, data):
        self.logger.debug("STATE: DISABLED")

        if data == self.MDB_POLL:  # POLL
            self.logger.debug("IN: Poll")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")

        elif data == self.MDB_RESET:  # RESET
            self.logger.debug("IN: Reset")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")
            self.state = "RESET"
            self.logger.info("PROCEED TO: RESET")

        elif data == self.MDB_READER_SETUP_CONFIG:  # SETUP CONFIG
            self.logger.debug("IN: Setup Config")
            self.send_data(self.MDB_READER_CONFIG_RESPONSE)
            self.logger.debug("OUT: Reader Config Response")

        elif data == self.MDB_READER_MINMAX_PRICES:
            self.logger.debug("IN: MinMax Prices")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")

        elif data == self.MDB_READER_ENABLE:
            self.logger.debug("IN: Reader Enable")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")
            self.state = "ENABLED"
            self.logger.info("PROCEED TO: ENABLED")

        elif data == self.MBD_READER_EXT_FEATURES:
            self.logger.debug("IN: Extended Features")
            self.send_data(self.MDB_EXT_FEATURES_RESPONSE)
            self.logger.debug("OUT: Extended Features Response")

        else:
            self.logger.info("IN: Unhandled Frame " + str(binascii.hexlify(data)))
            self.send_data(self.MDB_OUT_OF_SEQUENCE)
            self.logger.debug("OUT: Out Of Sequence")



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def handle_data_enabled(self, data):
        self.logger.debug("STATE: ENABLED")

        if data == self.MDB_POLL:  # POLL
            self.logger.debug("IN: Poll")
            if self.open_session:
                self.open_session = False
                self.timer = time.time()
                self.last_amount = self.available_callback(0)
                self.send_data(self.MDB_OPEN_SESSION)
                self.logger.debug("OUT: Open Session")
            else:
                self.send_display_order(self.default_display)

        elif data == self.MDB_READER_ENABLE:
            self.logger.debug("IN: Reader Enable")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")

        elif data == self.MDB_RESET:  # RESET
            self.logger.debug("IN: Reset")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")
            self.state = "RESET"
            self.logger.info("PROCEED TO: RESET")

        else:
            self.logger.info("IN Unhandled Frame " + str(binascii.hexlify(data)))
            self.send_data(self.MDB_OUT_OF_SEQUENCE)
            self.logger.debug("OUT: Out Of Sequence")


    
    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def handle_data_session(self, data):

        if self.substate == None:
            self.logger.debug("STATE: SESSION")

            if data == self.MDB_POLL:  # POLL
                self.logger.debug("IN: Poll")
                if time.time() - self.timer > self.TIMEOUT:
                    self.substate = "SESSION END"
                else:
                    self.send_display_order({'top': 'Getränk wählen','bot': 'Guthaben: ' + str(self.last_amount), 'duration': 2})

            elif data[0:2] == self.MDB_VEND_REQUEST:
                self.logger.debug("IN: Vend Request")
                self.slot = struct.unpack('>H', data[4:6])[0]
                self.last_amount = self.available_callback(self.slot)
                if self.last_amount:
                    self.logger.info("Request Approved, " + str(self.last_amount - 1) + " credits left")
                    self.send_data(self.MDB_VEND_APPROVED)
                    self.logger.debug("OUT: Vend Approved")
                else:
                    self.logger.info("Request Denied")
                    self.send_data(self.MDB_VEND_DENIED)
                    self.logger.debug("OUT: Vend Denied")

            elif data[0:2] == self.MDB_VEND_SUCCESFUL:
                self.logger.debug("IN: Vend Success")
                self.dispensed_callback(self.slot)
                self.send_data(self.MDB_CANCEL_REQUEST)
                self.logger.debug("OUT: Cancel Request")
                self.substate = "SESSION END"

            elif data[0:2] == self.MDB_VEND_CANCEL: # User put in coins
                self.logger.debug("IN: Vend Cancel")
                self.send_data(self.MDB_VEND_DENIED)
                self.logger.debug("OUT: Vend Denied")
                self.state = "ENABLED"
                self.logger.info("PROCEED TO: ENABLED")

            elif data == self.MDB_RESET:  # RESET
                self.logger.debug("IN: Reset")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")
                self.state = "RESET"
                self.logger.info("PROCEED TO: RESET")

            elif data == self.MDB_SESSION_COMPLETE:
                self.logger.debug("IN: Session Complete")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")
                self.substate = "SESSION END"

            else:
                self.logger.info("IN: Unhandled Frame " + str(binascii.hexlify(data)))
                self.send_data(self.MDB_OUT_OF_SEQUENCE)
                self.logger.debug("OUT: Out Of Sequence")

        
        elif self.substate == "SESSION END":
            self.logger.debug("STATE: SESSION END")
            self.substate = None

            if data == self.MDB_POLL:
                self.logger.debug("IN: Poll")
                self.send_data(self.MDB_END_SESSION)
                self.logger.debug("OUT: End Session")
                self.state = "ENABLED"
                self.logger.info("PROCEED TO: ENABLED")
                self.display_queue.put({'top': 'VCS', 'bot': '<3','duration': 3})

            else:
                self.logger.info("IN: Unhandled Frame " + str(binascii.hexlify(data)))
                self.send_data(self.MDB_OUT_OF_SEQUENCE)
                self.logger.debug("OUT: Out Of Sequence")



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def send_display_order(self, request):
        line1 = str(request['top'])
        line2 = str(request['bot'])
        duration = int(request['duration'])

        if duration > 25: duration = 25
        if duration < 1: duration = 1
        
        for line in (line1, line2):
            if len(line) < 16:
                missing = 16 - len(line)
                added_in_front = int(missing/2)
                added_in_back = missing - added_in_front
                line = added_in_front*' '+line+added_in_back*' '
            if len(line) > 16:
                line = line[0:16]

        duration_byte = bytearray(1)
        duration_byte[0] = duration*10
        duration_byte = bytes(duration_byte)

        line1 = bytes(line1.encode('utf8'))
        line2 = bytes(line2.encode('utf8'))

        self.send_data(self.MDB_DISPLAY_REQUEST + duration_byte + line1 + line2)
        self.logger.debug("OUT: Display Request")



    # name
    # INFO:
    # ARGS:
    # RETURNS:
    def __del__(self):
        # send session_complete after poll
        self.logger.debug("Closing connection!")
        frame = self.poll_data()
        while frame is None:
            frame = self.poll_data()
        if frame == self.MDB_POLL:
            self.logger.debug("IN: Poll")
            self.send_data(self.MDB_JUST_RESET)
            self.logger.debug("OUT: Just reset")
        else:
            self.logger.info("IN: Unhandled Frame {}".format(binascii.hexlify(frame)))
            self.send_data(self.MDB_JUST_RESET)
            self.logger.debug("OUT: Just reset")

        if self.ser.isOpen():
            self.ser.close()
