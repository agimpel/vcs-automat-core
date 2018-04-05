# Example of detecting and reading a block from a MiFare NFC card.
# Author: Manuel Fernando Galindo (mfg90@live.com)
#
# Copyright (c) 2016 Manuel Fernando Galindo
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import binascii
import array
from functools import reduce
import time
import serial
import logging

PN532_PREAMBLE                      = 0x00
PN532_STARTCODE1                    = 0x00
PN532_STARTCODE2                    = 0xFF
PN532_POSTAMBLE                     = 0x00

PN532_HOSTTOPN532                   = 0xD4
PN532_PN532TOHOST                   = 0xD5

# PN532 Commands
PN532_COMMAND_DIAGNOSE              = 0x00
PN532_COMMAND_GETFIRMWAREVERSION    = 0x02
PN532_COMMAND_GETGENERALSTATUS      = 0x04
PN532_COMMAND_READREGISTER          = 0x06
PN532_COMMAND_WRITEREGISTER         = 0x08
PN532_COMMAND_READGPIO              = 0x0C
PN532_COMMAND_WRITEGPIO             = 0x0E
PN532_COMMAND_SETSERIALBAUDRATE     = 0x10
PN532_COMMAND_SETPARAMETERS         = 0x12
PN532_COMMAND_SAMCONFIGURATION      = 0x14
PN532_COMMAND_POWERDOWN             = 0x16
PN532_COMMAND_RFCONFIGURATION       = 0x32
PN532_COMMAND_RFREGULATIONTEST      = 0x58
PN532_COMMAND_INJUMPFORDEP          = 0x56
PN532_COMMAND_INJUMPFORPSL          = 0x46
PN532_COMMAND_INLISTPASSIVETARGET   = 0x4A
PN532_COMMAND_INATR                 = 0x50
PN532_COMMAND_INPSL                 = 0x4E
PN532_COMMAND_INDATAEXCHANGE        = 0x40
PN532_COMMAND_INCOMMUNICATETHRU     = 0x42
PN532_COMMAND_INDESELECT            = 0x44
PN532_COMMAND_INRELEASE             = 0x52
PN532_COMMAND_INSELECT              = 0x54
PN532_COMMAND_INAUTOPOLL            = 0x60
PN532_COMMAND_TGINITASTARGET        = 0x8C
PN532_COMMAND_TGSETGENERALBYTES     = 0x92
PN532_COMMAND_TGGETDATA             = 0x86
PN532_COMMAND_TGSETDATA             = 0x8E
PN532_COMMAND_TGSETMETADATA         = 0x94
PN532_COMMAND_TGGETINITIATORCOMMAND = 0x88
PN532_COMMAND_TGRESPONSETOINITIATOR = 0x90
PN532_COMMAND_TGGETTARGETSTATUS     = 0x8A

PN532_RESPONSE_INDATAEXCHANGE       = 0x41
PN532_RESPONSE_INLISTPASSIVETARGET  = 0x4B

PN532_WAKEUP                        = 0x55

PN532_SPI_STATREAD                  = 0x02
PN532_SPI_DATAWRITE                 = 0x01
PN532_SPI_DATAREAD                  = 0x03
PN532_SPI_READY                     = 0x01

PN532_MIFARE_ISO14443A              = 0x00

PN532_ACK_STRING                    = "0000ff00ff00"
PN532_ACK_FRAME                     = b'\x00\x00\xFF\x00\xFF\x00'
PN532_EMPTY_FRAME                   = b'\x00\x00\xff\x03\xfd\xd5K\x00\xe0\x00'


def millis():
    return int(round(time.time() * 1000))


class PN532(object):

    def __init__(self, uart_port="COM5", uart_baudrate=115200):
        # set-up for logging of pn532. Level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
        self.loglevel = logging.WARNING
        self.logtitle = 'pn532'
        self.logger = logging.getLogger(self.logtitle)
        self.logger.setLevel(self.loglevel)
        self.status = False
        self.message = b''

        self.logger.debug("Port:" + uart_port)
        try:
            self.ser = serial.Serial(uart_port, uart_baudrate)
            self.ser.timeout = 2;
            self.status = True
        except serial.SerialException:
            self.logger.debug("Opening port error.")
            self.status = False

    def _uint8_add(self, a, b):
        """Add add two values as unsigned 8-bit values."""
        return ((a & 0xFF) + (b & 0xFF)) & 0xFF

    def _busy_wait_ms(self, ms):
        """Busy wait for the specified number of milliseconds."""
        start = time.time()
        delta = ms/1000.0
        while (time.time() - start) <= delta:
            pass

    def _write_frame(self, data):
        ack = False
        """Write a frame to the PN532 with the specified data bytearray."""
        assert data is not None and 0 < len(data) < 255, 'Data must be array of 1 to 255 bytes.'
        # Build frame to send as:
        # - Preamble (0x00)
        # - Start code  (0x00, 0xFF)
        # - Command length (1 byte)
        # - Command length checksum
        # - Command bytes
        # - Checksum
        # - Postamble (0x00)
        length = len(data)
        frame = bytearray(length+7)
        frame[0] = PN532_PREAMBLE
        frame[1] = PN532_STARTCODE1
        frame[2] = PN532_STARTCODE2
        frame[3] = length & 0xFF
        frame[4] = self._uint8_add(~length, 1)
        frame[5:-2] = data
        checksum = reduce(self._uint8_add, data, 0xFF)
        frame[-2] = ~checksum & 0xFF
        frame[-1] = PN532_POSTAMBLE
        # Send frame.
        self.ser.flushInput()
        while(not ack):
            self.ser.write(frame)
            ack = self._ack_wait(1000)
            time.sleep(0.3)
        return ack

    def _ack_wait(self, timeout):
        self.logger.debug("=== call to _ack_wait ===")
        ack = False
        rx_info = b''
        start_time = millis()
        current_time = start_time
        while((current_time - start_time) < timeout and not ack):
            time.sleep(0.12)
            rx_info += self.ser.read(self.ser.inWaiting())
            current_time = millis()
            if (PN532_ACK_STRING in binascii.hexlify(rx_info).decode()):
                self.logger.debug("String {} found in {}".format(PN532_ACK_STRING, binascii.hexlify(rx_info).decode()))
                ack = True

        if(ack):
            if(len(rx_info) > 6):
                rx_info = rx_info.split(PN532_ACK_FRAME)
                self.message = b''.join(rx_info)
                self.logger.debug("length > 6, message = {}".format(binascii.hexlify(self.message).decode()))
            else:
                self.message = rx_info
                self.logger.debug("length <= 6, message = {}".format(binascii.hexlify(self.message).decode()))
            self.ser.flush()
            return True
        else:
            self.logger.debug("Timeout")
            ack = False
            self.message = b''
            return False

    def _read_data(self, count):
        rx_info = b''
        if(self.message == b''):
            self._ack_wait(1000)
        else:
            rx_info = self.message
        rx_info = array.array('B', rx_info)
        return rx_info

    def _read_frame(self, length):
        """Read a response frame from the PN532 of at most length bytes in size.
        Returns the data inside the frame if found, otherwise raises an exception
        if there is an error parsing the frame.  Note that less than length bytes
        might be returned!
        """
        self.logger.debug("=== call to _read_frame ===")
        # Read frame with expected length of data.
        response = self._read_data(length+8)
        self.logger.debug("received data: {}".format(binascii.hexlify(response).decode()))
        self.logger.debug("toString: {}".format(response.tostring()))
        # Check frame starts with 0x01 and then has 0x00FF (preceeded by optional
        # zeros).
        if not (PN532_EMPTY_FRAME == response.tostring()):
            if response[0] != 0x00:
                raise RuntimeError('Response frame does not start with 0x01!')
            # Swallow all the 0x00 values that preceed 0xFF.
            offset = 1
            while response[offset] == 0x00:
                offset += 1
                if offset >= len(response):
                    raise RuntimeError('Response frame preamble does not contain 0x00FF!')
            if response[offset] != 0xFF:
                raise RuntimeError('Response frame preamble does not contain 0x00FF!')
            offset += 1
            if offset >= len(response):
                    raise RuntimeError('Response contains no data!')
            # Check length & length checksum match.
            frame_len = response[offset]
            if (frame_len + response[offset+1]) & 0xFF != 0:
                raise RuntimeError('Response length checksum did not match length!')
            # Check frame checksum value matches bytes.
            checksum = reduce(self._uint8_add, response[offset+2:offset+2+frame_len+1], 0)
            if checksum != 0:
                raise RuntimeError('Response checksum did not match expected value!')
            # Return frame data.
            return response[offset+2:offset+2+frame_len]
        else:
            return "no_card"

    def wakeup(self):
        msg = b'\x55\x55\x00\x00\x00'
        self.ser.write(msg)

    def call_function(self, command, response_length=0, params=[], timeout_sec=1):
        """Send specified command to the PN532 and expect up to response_length
        bytes back in a response.  Note that less than the expected bytes might
        be returned!  Params can optionally specify an array of bytes to send as
        parameters to the function call.  Will wait up to timeout_secs seconds
        for a response and return a bytearray of response bytes, or None if no
        response is available within the timeout.
        """
        # Build frame data with command and parameters.
        data = bytearray(2+len(params))
        data[0] = PN532_HOSTTOPN532
        data[1] = command & 0xFF
        data[2:] = params
        # Send frame and wait for response.
        if not self._write_frame(data):
            return None
        # Read response bytes.
        response = self._read_frame(response_length+2)
        # Check that response is for the called function.
        if not (response == "no_card"):
            if not (response[0] == PN532_PN532TOHOST and response[1] == (command+1)):
                raise RuntimeError('Received unexpected command response!')
            # Return response data.
            return response[2:]
        else:
            return response

    def begin(self):
        """Initialize communication with the PN532.  Must be called before any
        other calls are made against the PN532.
        """
        self.wakeup()

    def get_firmware_version(self):
        """Call PN532 GetFirmwareVersion function and return a tuple with the IC,
        Ver, Rev, and Support values.
        """
        response = self.call_function(PN532_COMMAND_GETFIRMWAREVERSION, 4)
        if response is None:
            raise RuntimeError('Failed to detect the PN532!  Make sure there is sufficient power (use a 1 amp or greater power supply), the PN532 is wired correctly to the device, and the solder joints on the PN532 headers are solidly connected.')
        return (response[0], response[1], response[2], response[3])

    def SAM_configuration(self):
        """Configure the PN532 to read MiFare cards."""
        # Send SAM configuration command with configuration for:
        # - 0x01, normal mode
        # - 0x14, timeout 50ms * 20 = 1 second
        # - 0x01, use IRQ pin
        # Note that no other verification is necessary as call_function will
        # check the command was executed as expected.
        self.call_function(PN532_COMMAND_SAMCONFIGURATION, params=[0x01, 0x14, 0x01])

    def read_passive_target(self, card_baud=PN532_MIFARE_ISO14443A):
        """Wait for a MiFare card to be available and return its UID when found.
        Will wait up to timeout_sec seconds and return None if no card is found,
        otherwise a bytearray with the UID of the found card is returned.
        """
        # Send passive read command for 1 card.  Expect at most a 7 byte UUID.
        response = self.call_function(PN532_COMMAND_INLISTPASSIVETARGET,
                                      params=[0x01, card_baud],
                                      response_length=17)
        # If no response is available return None to indicate no card is present.
        if response is None:
            return None
        if not (response == "no_card"):
            # Check only 1 card with up to a 7 byte UID is present.
            if response[0] != 0x01:
                raise RuntimeError('More than one card detected!')
            if response[5] > 7:
                raise RuntimeError('Found card with unexpectedly long UID!')
            # Return UID of card.
            return response[6:6+response[5]]
        else:
            return None
