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

    # __init__
    # INFO:     Sets up logging of this class and opens the serial connection to the MDB reader.
    # ARGS:     -
    # RETURNS:  -
    def __init__(self):
        # set-up for logging of mdbh. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.INFO
        self.logtitle = 'mdbh'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)

        Thread.__init__(self, daemon=True)
        self.is_running = False

        # Open up the serial connection and set up initial variables
        self.ser = serial.Serial('/dev/ttyS0', 115200, timeout=0.1) # find port with 'python -m serial.tools.list_ports'
        self.open_session = False
        self.state = "RESET"
        self.substate = None
        self.display_queue = queue.Queue()
        self.display_timeout = 0
        self.dispensed_callback = None
        self.available_callback = None
        self.last_amount = 0 # amount of credits left for user

        self.default_display = {'top': 'VCS-Bierautomat', 'bot': 'Legi einscannen', 'duration': 1}

    # exit
    # INFO:     Can be triggered from main thread to shut this thread down.
    # ARGS:     -
    # RETURNS:  -
    def exit(self):
        self.logger.info("SHUTDOWN")
        self.is_running = False

    # run
    # INFO:     Main thread of this class. Checks if new data was received from the MDB reader and processes it according to the current state of operation.
    # ARGS:     -
    # RETURNS:  -
    def run(self):

        self.is_running = True

        while self.is_running:
            # Sleep to prevent timing issues with the MDB reader
            time.sleep(0.1)

            # Read data from MDB reader
            data = self.poll_data()

            # Process data according to current state
            if data is not None:

                # Only if the vending machine is polling and there is a display event requested, the display text can be send
                if data == self.MDB_POLL and self.display_queue.empty() is False:
                    self.send_display_order(self.display_queue.get(), priority = True)

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

        # Force notifying the MDB reader about a shutdown of this thread
        self.__del__()

    # set_dispensed_callback
    # INFO:     Is set by the main class to link to a function handling the reporting of a vend to the APIs.
    # ARGS:     function (function) -> callback
    # RETURNS:  -
    def set_dispensed_callback(self, function):
        self.dispensed_callback = function

    # set_available_callback
    # INFO:     Is set by the main class to link to a function returning the amount of credits the current user has left.
    # ARGS:     function (function) -> callback
    # RETURNS:  -
    def set_available_callback(self, function):
        self.available_callback = function

    # poll_data
    # INFO:     Reads the MDB reader and preprocesses the data frame for further use in this class.
    # ARGS:     -
    # RETURNS:  Either data (bytearray) if the reader sent a frame, or None otherwise.
    def poll_data(self):
        # Read only first byte to see whether the reader actually sent a frame.
        s = self.ser.read(1)
        if s == self.MDB2PC_NAK:
            self.logger.debug("MDB2PC: [IN] NAK")
        if s == self.MDB2PC_ACK:
            self.logger.debug("MDB2PC: [IN] ACK")
        if s == self.MDB2PC_FRAME_START:
            # Read the complete data frame and crop to the frame contents
            s = s + self.ser.read(10)
            start = s.find(self.MDB2PC_FRAME_BEGIN) + 2
            end = s.find(self.MDB2PC_FRAME_STOP, start)
            data = s[start:end]
            self.logger.debug("MDB2PC: [IN] MDB Frame " + str(binascii.hexlify(data)))
            self.ser.write(self.MDB2PC_ACK)
            self.logger.debug("MDB2PC: [OUT] ACK")
            return data
        return None

    # send_data
    # INFO:     Inserts data sent to the MDB reader into the data frame.
    # ARGS:     data (bytearray) -> Data to be sent to the MDB reader
    # RETURNS:  -
    def send_data(self, data):
        self.ser.write(self.MDB2PC_FRAME_BEGIN + data + self.MDB2PC_FRAME_STOP)
        self.ser.flush()

    # handle_data_reset
    # INFO:     Processes the data sent from the MDB reader if the current state is RESET. It follows the general MDB protocol to start up the vending machine into the DISABLED state.
    # ARGS:     data (bytearray) -> the preprocessed data sent from the MDB reader
    # RETURNS:  -
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

    # handle_data_disabled
    # INFO:     Processes the data sent from the MDB reader if the current state is DISABLED. It follows the general MDB protocol, sending general information about the MDB reader to the vending machine to finalise preparation for the ENABLED state.
    # ARGS:     data (bytearray) -> the preprocessed data sent from the MDB reader
    # RETURNS:  -
    def handle_data_disabled(self, data):
        self.logger.debug("STATE: DISABLED")

        if data == self.MDB_POLL:
            self.logger.debug("IN: Poll")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")

        elif data == self.MDB_RESET:
            self.logger.debug("IN: Reset")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")
            self.state = "RESET"
            self.logger.info("PROCEED TO: RESET")

        elif data == self.MDB_READER_SETUP_CONFIG:
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

    # handle_data_enabled
    # INFO:     Processes the data sent from the MDB reader if the current state is ENABLED. It follows the general MDB protocol to initiate the SESSION state used for vending.
    # ARGS:     data (bytearray) -> the preprocessed data sent from the MDB reader
    # RETURNS:  -
    def handle_data_enabled(self, data):
        self.logger.debug("STATE: ENABLED")

        if data == self.MDB_POLL:
            self.logger.debug("IN: Poll")
            # if the open_session flag is set to True, the vending machine should start a vending session. Otherwise, the default display text is displayed.
            if self.open_session:
                self.open_session = False
                self.timer = time.time()
                self.last_amount = self.available_callback(0)
                self.send_data(self.MDB_OPEN_SESSION)
                self.logger.debug("OUT: Open Session")
                self.state = "SESSION"
                self.substate = None
                self.logger.info("PROCEED TO: SESSION")
            else:
                self.send_display_order(self.default_display)

        elif data == self.MDB_READER_ENABLE:
            self.logger.debug("IN: Reader Enable")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")

        elif data == self.MDB_RESET:
            self.logger.debug("IN: Reset")
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")
            self.state = "RESET"
            self.logger.info("PROCEED TO: RESET")

        else:
            self.logger.info("IN Unhandled Frame " + str(binascii.hexlify(data)))
            self.send_data(self.MDB_OUT_OF_SEQUENCE)
            self.logger.debug("OUT: Out Of Sequence")

    # handle_data_session
    # INFO:     Processes the data sent from the MDB reader if the current state is SESSION. It follows the general MDB protocol to handle the vending including any cancellation processes. The SESSION state is divided into multiple substates that correspond to the position within the vend process. The substates are not part of the standard MDB protocol, but are added to reduce complexity.
    # ARGS:     data (bytearray) -> the preprocessed data sent from the MDB reader
    # RETURNS:  -
    def handle_data_session(self, data):

        # If the program entered the SESSION state just yet, the substate is set to None.
        if self.substate == None:
            self.logger.debug("STATE: SESSION")

            # As long as the timeout is not reached, a new display text is shown on the vending machine. After the timeout, the session is cancelled
            if data == self.MDB_POLL:
                self.logger.debug("IN: Poll")
                if time.time() - self.timer > self.TIMEOUT:
                    self.substate = "SESSION CANCEL"
                else:
                    self.send_display_order({'top': 'Slot aussuchen','bot': 'Guthaben: ' + str(self.last_amount), 'duration': 5})

            # If a vend is requested (a selection button was pressed), read the amount of credits of user via callback and either approve or cancel vend
            elif data[0:2] == self.MDB_VEND_REQUEST:
                self.logger.debug("IN: Vend Request")
                self.slot = struct.unpack('>H', data[4:6])[0]
                self.last_amount = self.available_callback(self.slot)
                if self.last_amount:
                    self.logger.info("Request Approved, " + str(self.last_amount - 1) + " credits left")
                    self.send_data(self.MDB_VEND_APPROVED)
                    self.logger.debug("OUT: Vend Approved")
                    self.substate = "VEND APPROVED"
                else:
                    self.logger.info("Request Denied")
                    self.send_data(self.MDB_VEND_DENIED)
                    self.logger.debug("OUT: Vend Denied")
                    self.substate = "VEND CANCEL"

            elif data[0:2] == self.MDB_VEND_CANCEL: # User put in coins
                self.logger.debug("IN: Vend Cancel")
                self.send_data(self.MDB_CANCEL_REQUEST)
                self.logger.debug("OUT: Cancel Request")
                self.substate = "SESSION END"

            elif data == self.MDB_RESET:
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

        # A VEND CANCEL substate indicates the vend was stopped either by the program or the user. No vend should be reported, as no drink was released.
        elif self.substate == "VEND CANCEL":
            self.logger.debug("STATE: VEND CANCEL")

            if data == self.MDB_POLL:
                self.logger.debug("IN: Poll")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")

            elif data[0:2] == self.MDB_VEND_CANCEL: # User put in coins
                self.logger.debug("IN: Vend Cancel")
                self.send_data(self.MDB_CANCEL_REQUEST)
                self.logger.debug("OUT: Cancel Request")
                self.substate = "SESSION END"

            elif data == self.MDB_RESET:  # RESET
                self.logger.debug("IN: Reset")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")
                self.state = "RESET"
                self.logger.info("PROCEED TO: RESET")
                self.substate = None

            elif data == self.MDB_SESSION_COMPLETE:
                self.logger.debug("IN: Session Complete")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")
                self.substate = "SESSION END"

            else:
                self.logger.info("IN: Unhandled Frame " + str(binascii.hexlify(data)))
                self.send_data(self.MDB_OUT_OF_SEQUENCE)
                self.logger.debug("OUT: Out Of Sequence")

        # A VEND APPROVED substate indicates the user has sufficient credits and the vend can be performed
        elif self.substate == "VEND APPROVED":
            self.logger.debug("STATE: VEND APPROVED")

            if data == self.MDB_POLL:
                self.logger.debug("IN: Poll")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")

            # The drink was released, report vend to APIs
            elif data[0:2] == self.MDB_VEND_SUCCESFUL:
                self.logger.debug("IN: Vend Success")
                self.dispensed_callback(self.slot)
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")
                self.substate = "SESSION CANCEL"

            elif data[0:2] == self.MDB_VEND_CANCEL: # User put in coins
                self.logger.debug("IN: Vend Cancel")
                self.send_data(self.MDB_CANCEL_REQUEST)
                self.logger.debug("OUT: Cancel Request")
                self.substate = "SESSION END"

            elif data == self.MDB_RESET:
                self.logger.debug("IN: Reset")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")
                self.state = "RESET"
                self.logger.info("PROCEED TO: RESET")
                self.substate = None

            elif data == self.MDB_SESSION_COMPLETE:
                self.logger.debug("IN: Session Complete")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")
                self.substate = "SESSION END"

            else:
                self.logger.info("IN: Unhandled Frame " + str(binascii.hexlify(data)))
                self.send_data(self.MDB_OUT_OF_SEQUENCE)
                self.logger.debug("OUT: Out Of Sequence")

        # Either due to successfull vend or a cancellation, the SESSION CANCEL substate negotiates the return to the ENABLED state to the vending machine.
        elif self.substate == "SESSION CANCEL":
            self.logger.debug("STATE: SESSION CANCEL")

            if data == self.MDB_POLL:
                self.logger.debug("IN: Poll")
                self.send_data(self.MDB_CANCEL_REQUEST)
                self.logger.debug("OUT: Cancel Request")
                self.substate = "SESSION END"

            # Sending MDB_SESSION_COMPLETE forces the vending machine to stop its session, leading to it polling.
            elif data == self.MDB_SESSION_COMPLETE:
                self.logger.debug("IN: Session Complete")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")

            else:
                self.logger.info("IN: Unhandled Frame " + str(binascii.hexlify(data)))
                self.send_data(self.MDB_OUT_OF_SEQUENCE)
                self.logger.debug("OUT: Out Of Sequence")

        # After the closing of the session is negotiated, the SESSION END substate performs the switch to the ENABLED state
        elif self.substate == "SESSION END":
            self.logger.debug("STATE: SESSION END")

            if data == self.MDB_POLL:
                self.logger.debug("IN: Poll")
                self.send_data(self.MDB_END_SESSION)
                self.logger.debug("OUT: End Session")
                self.state = "ENABLED"
                self.logger.info("PROCEED TO: ENABLED")
                self.substate = None
                self.display_queue.put({'top': 'VCS', 'bot': '<3', 'duration': 3})

            elif data == self.MDB_SESSION_COMPLETE:
                self.logger.debug("IN: Session Complete")
                self.send_data(self.MDB_ACK)
                self.logger.debug("OUT: ACK")

            else:
                self.logger.info("IN: Unhandled Frame " + str(binascii.hexlify(data)))
                self.send_data(self.MDB_OUT_OF_SEQUENCE)
                self.logger.debug("OUT: Out Of Sequence")




    # send_display_order
    # INFO:     Queues a display request to show text on the vending machine's display. The request consists of two lines of text and a duration for which the text should be shown. If the priority flag is set to True, the text is displayed even if another text's duration is not yet reached.
    # ARGS:     request (array) -> content of the display request: top line, bottom line and duration; priority (bool, optional) whether to overwrite existing text
    # RETURNS:  -
    def send_display_order(self, request, priority = False):

        # Check if previous text is not finished or the new display request is not prioritized. If so, just send ACK and nothing happens.
        if priority is False and self.display_timeout > time.time():
            self.send_data(self.MDB_ACK)
            self.logger.debug("OUT: ACK")
            return

        # Preprocess array contents
        lines = [str(request['top']), str(request['bot'])]
        duration = int(request['duration'])

        # Max duration is 25s, min duration is 0.1s
        if duration > 25: duration = 25
        if duration < 0.1: duration = 0.1

        # Save timeout of current text. Shorten it by almost one second, as this is roughly the time between POLLs of the MDB reader
        self.display_timeout = time.time() + duration - 0.9
        
        # Build text lines (max 16 chars) by centering the individual lines
        for line in range(0,len(lines)):
            if len(lines[line]) < 16:
                missing = 16 - len(lines[line])
                added_in_front = int(missing/2)
                added_in_back = missing - added_in_front
                lines[line] = added_in_front*' '+lines[line]+added_in_back*' '
            if len(lines[line]) > 16:
                lines[line] = lines[line][0:16]

        # Build the data to be sent to the MDB reader, see MDB documentation for formatting
        duration_byte = bytearray(1)
        duration_byte[0] = int(duration*10)
        duration_byte = bytes(duration_byte)

        # encode lines into bytes. Check encoding for issues with Umlauts
        line1 = bytes(lines[0].encode('utf8'))
        line2 = bytes(lines[1].encode('utf8'))

        # Send display request to MDB reader
        self.send_data(self.MDB_DISPLAY_REQUEST + duration_byte + line1 + line2)
        self.logger.debug("OUT: Display Request")




    # __del__
    # INFO:     Informs the vending machine about the shutdown and gracefully kills the connection to the MDB reader.
    # ARGS:     -
    # RETURNS:  -
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
