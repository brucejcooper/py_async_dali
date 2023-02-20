
import asyncio
import logging
import threading
from enum import Enum
from typing import List

import hid

from .bus_transciever import (AbstractDaliAddress, AddressedCommand, BadFrame,
                              DaliBusTransciever, DirectArcPowerCommand,
                              NakMessage, NumericResponseMessage,
                              SpecialCommand)
from .types import (DaliCommandCode, FramingException, MessageSource,
                    SpecialCommandCode, ItemDelta)

_LOGGER = logging.getLogger(__name__)

class MessageType(Enum):
    NAK = 0x71
    RESPONSE = 0x72
    TX_COMPLETE = 0x73
    BROADCAST_RECEIVED = 0x74
    FRAMING_ERROR = 0x77


class TridonicDali(DaliBusTransciever):
    VENDOR_ID=0x17b5
    PRODUCT_ID=0x0020
    transceivers: List[DaliBusTransciever] = []

    def __init__(self, dev: hid.Device, evt_loop=None) -> None:
        DaliBusTransciever.__init__(self)
        self.next_sequence = 1
        self.dev = dev
        self._opened = False
        self.manufacturer = dev.manufacturer
        self.model = dev.product
        self.serial = dev.serial


        # See if we can look up Manufacturer and Model information from pyudev

        self.outstanding_commands = dict()

        if evt_loop is None:
            self.evt_loop = asyncio.get_event_loop()
        else:
            self.evt_loop = evt_loop

        # Add a default callback handler to deal with Responses
        self._new_message_callbacks.append(self._resolve_futures)
        self._stop_listening = threading.Event()


    @property
    def unique_id(self):
        return "tridonic-usb-{}".format(self.dev.serial)


    @classmethod
    async def _transciever_scan(cls) -> List[ItemDelta[DaliBusTransciever]]:  
        """This can be called multiple times, and it will return any _new_"""

        added = []
        removed = list(cls.transceivers)
        _LOGGER.debug("Scanning for transmitters")
        for h in hid.enumerate(TridonicDali.VENDOR_ID, TridonicDali.PRODUCT_ID):
            serial = h['serial_number']

            existing = [x for x in cls.transceivers if x.dev.serial == serial]
            if len(existing) == 0:
                hiddev = hid.Device(h['vendor_id'], h['product_id'], serial)

                bus = TridonicDali(hiddev)
                cls.transceivers.append(bus)
                added.append(bus)
            else:
                removed.remove(existing[0])
        return ItemDelta(added, removed)

    def __repr__(self):
        return self.unique_id

    async def __aenter__(self):
        self.open()
        return self

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        await self.close()

    def open(self):
        self._stop_listening.clear()
        self._read_thread = threading.Thread(target=self.read_loop, daemon=True)
        self._opened = True
        self._read_thread.start()



    def _resolve_futures(self, msg):
        """This system is event driven, but we want to make it a bit easier to use.  This method listens to
         all incoming messages to see if they correlate to ones that were sent out.  If we find one, we resolve it's future"""

        future = self.outstanding_commands.get(msg.sequence_number, None)
        if future is not None:
            if isinstance(msg, NumericResponseMessage):
                future.set_result(msg.value)
                del self.outstanding_commands[msg.sequence_number]
            elif isinstance(msg, NakMessage):
                future.set_result(None)
                del self.outstanding_commands[msg.sequence_number]
            elif isinstance(msg, BadFrame):
                future.set_exception(FramingException("Framing Error"))
                del self.outstanding_commands[msg.sequence_number]

    def read_loop(self):
        """Thread based reader of data off the USB device.  When it receives a message, call back (via asyncio) to registered receivers"""
        while not self._stop_listening.is_set():
            try:
                ret = self.receive()
                if ret is not None:
                    for callback in self._new_message_callbacks:
                        self.evt_loop.call_soon_threadsafe(callback, ret)
            except:
                _LOGGER.error("Got Exception", exc_info=1)
                self.evt_loop.run_until_complete(self.close())
        _LOGGER.debug("Reader finished")

    async def close(self):
        """Stops listening and closes the HID device"""
        self._stop_listening.set()
        self.dev.close()  # This will cause any active call to read to throw an exception.
        self._opened = False

    def get_seq(self):
        """Gets a new sequence number for correlating messages"""
        newseq = self.next_sequence
        self.next_sequence = self.next_sequence + 1  # Note: Not thread safe
        if self.next_sequence > 255:
            self.next_sequence = 1  # Sequence 0 is reserved for external entities
        return newseq

    def _send(self, cmd: int, length=16, repeat=1):
        """Sends a DALI message to the tridonic USB system.
           Bit pattern Reverse-engineered by USB sniffing.

           Packet size: 64 bytes - most of them 0x00

           * pkt[0] = Direction
             * 0x12 From Me (As opposed to a different leader on the bus)
           * Pkt[1] = Sequence Number (for correlating responses)
           * pkt[2] = Number of times to repeat command
             * 0x20 Repeat twice
             * 0x00 Send once
           * pkt[3] = Type
             * 0x03 - 16 Bit Gear Command
             * 0x04 - 24 bit Device Command
             * 0x05 - DA24 Config command - not 100% sure what the difference is between this and the other.
           * pkt[4] = 0x00
           * pkt[5] = Bits 16-23 of message, or 0 if size is less than 24 bits
           * pkt[6] = Bits 8-15 of message - Be it the address, or the special command
           * pkt[7] = Bits 0-7 of the message
           * Remainder = 0x00
        
        example command for START QUIESCENT Command
        12 01 20 06 00 ff fe 1d 00 00 00 00 00 00 00 00...

        Returns a Future that will be resolved when the response or NAK is received back.
        """
        response = asyncio.Future()

        if not self._opened:
            response.set_exception(Exception("Device not open"))
            return response

        seq = self.get_seq()
        data = bytearray(64)  # Transmitted packets are 64 bytes wide, but most of them (all but the first 8) are 0x00
        data[0] = MessageSource.SELF.value  # USB side command
        data[1] = seq
        if repeat == 2:
            data[2] = 0x20

        if length == 16:
            data[3] = 0x03
        else:
            if length == 24:
                data[3] = 0x04
            elif length == 25:  # Magic value for DA24 extended command.
                data[3] = 0x06
            else:
                response.set_exception(Exception("Invalid length"))
                return response
            data[5] = (cmd >> 16) & 0xFF

        data[6] = (cmd >> 8) & 0xFF
        data[7] = cmd & 0xFF
        _LOGGER.debug("Transmitting %s", bytes(data))

        self.dev.write(bytes(data))

        # To make things easier on implementers, we automatically correlate Commands and responses via a future
        self.outstanding_commands[seq] = response
        self.last_command = response
        return response

    def receive(self, timeout=None):
        """Raw data received from DALI USB
           Bit pattern Reverse-engineered by USB sniffing.

           Packet size: 16 bytes - most of them 0x00

           * pkt[0] = Direction
             * 0x11 From a different bus leader
             * 0x12 Was sent by this device
           * Pkt[1] = Type
             * 0x71 = NAK message
             * 0x72 = Response to command
             * 0x73 = Command was transmitted to the bus
             * 0x74 = Broadcast received
             * 0x76 = ?
             * 0x77 = Framing Error
           * pkt[3] = Bits 16-23 of message, or 0 if size is less than 24 bits
           * pkt[4] = Bits 8-15 of message - Be it the address, or the special command
           * pkt[5] = Bits 0-7 of the message
           * pkt[6-7] = ?
           * pkt[8] = Sequence Number, for correlating with transmitted messages.  Appears to only be set for stuff we sent ourselves (makes sense)

           This method is not asyncio friendly.  Call from a synchronous thread.
        """
        if not self._opened:
            raise Exception("Device not open")
        data = self.dev.read(16) # This will block until something is read, a timeout occurs, or the HID device is closed
        _LOGGER.debug("read %s(%d bytes)", data, len(data))
        if data is None or len(data) == 0:
            return None

        msg = None
        try:
            high_byte = data[3]
            mid_byte = data[4]
            low_byte = data[5]
            sequence_number = data[8]
            direction = MessageSource(data[0])
            message_type = MessageType(data[1])

            if message_type == MessageType.NAK:
                msg = NakMessage(self, direction, sequence_number)
            elif message_type == MessageType.RESPONSE:
                msg = NumericResponseMessage(self, direction, sequence_number, low_byte)
            else:
                if SpecialCommandCode.is_special_command(mid_byte):
                    msg = SpecialCommand(self, direction, sequence_number, SpecialCommandCode(mid_byte), low_byte)
                elif mid_byte & 0x01 == 0:
                    msg = DirectArcPowerCommand(self, direction, sequence_number, AbstractDaliAddress.parse_address(mid_byte), low_byte)
                else:
                    msg = AddressedCommand(self, direction, sequence_number, AbstractDaliAddress.parse_address(mid_byte), DaliCommandCode(low_byte))
        except:
            _LOGGER.warn("Could not process %s %s 0x%02x%02x%02x %d", direction, message_type, high_byte, mid_byte, low_byte, sequence_number, exc_info=1)

        return msg
