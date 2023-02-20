import asyncio
import logging
from typing import Any, Awaitable, List, NamedTuple

from .address import AbstractDaliAddress, DaliGearAddress, DaliGearGroupAddress
from .gear import DaliGear, DaliGearGroup
from .types import (DaliCommandCode, DaliException, FramingException,
                    MessageSource, SearchAddressClashException,
                    SpecialCommandCode, ItemDelta)


_LOGGER = logging.getLogger(__name__)


class SearchAddressSender:
    """When transmitting new values for search address, only transmit the ones that change"""
    
    def __init__(self, drv):
        self.drv = drv
        self.lastH = None
        self.lastM = None
        self.lastL = None

    async def send(self, addr):
        l = addr & 0xFF
        m = (addr >> 8) & 0xFF
        h = (addr >> 16) & 0xFF

        if l != self.lastL:
            await self.drv.send_special_cmd(DaliCommandCode.SearchAddrL, l)
            self.lastL = l
        if m != self.lastM:
            await self.drv.send_special_cmd(DaliCommandCode.SearchAddrM, m)
            self.lastM = m
        if h != self.lastH:
            await self.drv.send_special_cmd(DaliCommandCode.SearchAddrH, h)
            self.lastH = h


class DaliBusTransciever:
    devices: List[DaliGear]
    groups: List[DaliGearGroup]
    transcievers: List['DaliBusTransciever'] = []
    manufacturer: str|None
    model: str|None
    serial: str|None
    
    def __init__(self) -> None:
        self._new_message_callbacks = []
        self.devices = [DaliGear(self, DaliGearAddress(index)) for index in range(0,64)]
        self.groups = [DaliGearGroup(self, DaliGearGroupAddress(index), []) for index in range(0,16)]
        self.manufacturer = None
        self.model = None
        self.serial = None

    @property
    def unique_id(self):
        raise Exception("Not Implemented")

    @property
    def present_gear(self):
        return [g for g in self.devices if g.present]

    @property
    def present_groups(self):
        return [g for g in self.groups if g.has_gear]


    @classmethod
    async def scan_for_transcievers(cls) -> ItemDelta['DaliBusTransciever']:
        subclz = cls.__subclasses__()

        res = ItemDelta([], [])
        for sc in subclz:
            delta = await sc._transciever_scan()
            res.extend(delta)
            cls.transcievers.extend(delta.added)
            for to_remove in delta.removed:
                cls.transcievers.remove(to_remove)
        return res

    def _send(self, data: int, length: int = 16, repeat: int = 1)-> Awaitable[int|None]:
        raise Exception("Not Implemented")

    def send_direct_arc_power(self, address: AbstractDaliAddress, level) -> Awaitable[None]:
        return self._send((address.code << 8) | level)

    def send_cmd(self, address: AbstractDaliAddress, cmd: DaliCommandCode, repeat=1) -> Awaitable[int|None]:
        return self._send((address.code << 8) | 0x0100 | cmd.value, repeat=repeat)

    def send_special_cmd(self, special_cmd: SpecialCommandCode, param: int = 0, repeat=1) -> Awaitable[None]:
        return self._send((special_cmd.value << 8) | param, repeat=repeat)
    

    def broadcast(self, cmd: DaliCommandCode, repeat=1) -> Awaitable[None]:
        return self._send(0xFF << 8 | cmd.value, repeat=repeat)

    def start_quiescent(self) -> Awaitable[None]:
        return self._send(0xFFFE1D, length=25, repeat=2)

    def stop_quiescent(self) -> Awaitable[None]:
        return self._send(0xFFFE1E, length=25, repeat=2)


    def add_message_callback(self, cb):
        self._new_message_callbacks.append(cb)

    def remove_message_callback(self, cb):
        self._new_message_callbacks.remove(cb)

    async def __aenter__(self):
        pass # By default, do nothing

    async def __aexit__(self, exc_type, exc_value, exc_traceback):
        pass # By default, do nothing

    async def scan_for_gear(self):
        for gear in self.devices:
            _LOGGER.debug("Scanning %s", gear)
            await gear.fetch_deviceinfo()

        for group in self.groups:
            bit_mask = 1 << group.address.group_num
            group.group_members =  [g for g in self.devices if g.groups & bit_mask != 0]
            await group.fetch_deviceinfo()

        return self.devices


    async def compare(self, search, address_sender):
        """
        Compares the supplied search value with items on the bus. 
        Returns: 
          int: how many devices (0, 1, or 2 to represent more than 1) devices with the search address equal 
               to or lower than the supplied value
        """
        # print("Compare 0x{:06x}".format(search))
        await address_sender.send(search)
        try:
            found = await self.send_special_cmd(DaliCommandCode.Compare)
            if found == 0xFF:
                # Precisely one device is equal to or less than high
                return 1
            elif found == None:
                # No devices found under
                return 0
            else:
                raise Exception("Illegal Response from search command")

        except FramingException as ex:
            # This means there are multiple devices equal or under high
            return 2


    async def _commission_search_gear(self, start=0):
        """Performs a binary search of the address search space, finding the participating gear with
           the lowest search address
        """
        low = start
        high = 0xFFFFFF

        sender = SearchAddressSender(self)
        while True:
            mid = int((low+high)/2) # Start in the middle
            res = await self.compare(mid, sender)

            if low == high:
                if res == 1:
                    return mid
                elif res == 2:
                    # There is a search address clash.
                    raise SearchAddressClashException()
                else:
                    # No devices found at all.
                    return None

            if res == 0:
                # zero devices below or equal to mid
                low = mid+1
            else:
                # 1 or more devices below or equal to mid, but we don't know which
                high = mid


    async def commission(self):
        # Terminate any outstanding initialise.
        await self.send_special_cmd(DaliCommandCode.Terminate, 0)
        try:

            # TODO start quiescent mode (24 bit command.)

            # Put devices in initialisation mode. 
            await self.send_special_cmd(DaliCommandCode.Initialise, repeat=2)


            # Clear out any existing short addresses
            await self.send_special_cmd(DaliCommandCode.SetDTR0, 0xFF)
            await self.broadcast(DaliCommandCode.SetShortAddress, repeat=2)

            # Reset operating mode
            await self.send_special_cmd(DaliCommandCode.SetDTR0, 128)
            await self.broadcast(DaliCommandCode.SetOperatingMode, repeat=2)

            # Remove devices from groups
            for group in range(16):
                await self.broadcast(DaliCommandCode.RemoveFromGroup | group, repeat=2)

            # Randomise the search addresses for all devices. 
            await self.send_special_cmd(DaliCommandCode.Randomise, repeat=2)
            await asyncio.sleep(0.1)  

            
            finished = False
            search_floor = 0

            available_short_addresses = list(range(64))

            while not finished:
                # We know that there are no more devices less than search floor, so pass that in as a starting point.
                # TODO strictly, we could make this faster, as we know which segments of the search have stuff in and which don't.
                try:
                    found = await self._commission_search_gear(search_floor)

                    if found:
                        short_addr = available_short_addresses.pop(0)
                        shifted = (short_addr << 1) | 0x01
                        await self.send_special_cmd(DaliCommandCode.ProgramShortAddress, shifted)
                        queried_short_addr = await self.send_special_cmd(DaliCommandCode.QueryShortAddress)

                        if queried_short_addr == shifted:
                            # Good, the device took the address
                            await self.send_special_cmd(DaliCommandCode.Withdraw)
                        else:
                            raise DaliException("Short Address did not stick (Returned {:02x} instead of {:02x})".format(queried_short_addr, shifted))
                        search_floor = found + 1
                    else:
                        # print("No more devices found")
                        finished = True
                except SearchAddressClashException:
                    # Two devices managed to settle on the same search address.  Re-randomise any gear that hasn't already been allocated
                    search_floor = 0
        finally:
            # Make sure we've terminated our commission process
            await self.send_special_cmd(DaliCommandCode.Terminate, 0)
                


class DaliMessage: 
    """Represents a message being transmitted or received by the driver"""
    transciever: DaliBusTransciever
    source: MessageSource
    sequence_number: int

    def __init__(self, transciever: DaliBusTransciever, source: MessageSource, sequence_number: int):
        self.transciever = transciever
        self.source = source
        self.sequence_number = sequence_number

    def __repr__(self):
        return "{} ({})".format(self.source.name, self.sequence_number)
    
    @property
    def affected_gear(self):
        """Each message may affect one or more gear on its bus.  This property tells us
        which (already discovered) gear would be affected"""
        return []

    def get_affected_groups(self, affected_gear):
        """Once we've worked out which devices are affected by a message, we need to work out
        which groups also incidentally get affected."""

        mask = 0
        for g in affected_gear:
            mask = mask | g.groups

        return [g for g in self.transciever.groups if mask & g.mask != 0]

class ResponseMessage(DaliMessage):
    pass

class NakMessage(ResponseMessage):
    def __repr__(self):
        return super().__repr__() + " NAK"

class AddressedMessage(DaliMessage):
    address: AbstractDaliAddress

    def __init__(self, transciever: DaliBusTransciever, source: MessageSource, sequence_number: int, address: AbstractDaliAddress):
        super().__init__(transciever, source, sequence_number)
        self.address = address

    @property
    def affected_gear(self):
        return [g for g in self.transciever.devices if self.address.matches_gear(g)]



class DirectArcPowerCommand(AddressedMessage):
    value: int

    def __init__(self, transciever: DaliBusTransciever, source: MessageSource, sequence_number: int, address: AbstractDaliAddress, value: int):
        super().__init__(transciever, source, sequence_number, address)
        self.value = value

    def __repr__(self):
        return super().__repr__() + " DAPC({}, {})".format(self.address, self.value)


class NumericResponseMessage(ResponseMessage):
    value: int
    def __init__(self, transciever: DaliBusTransciever, source: MessageSource, sequence_number: int, value: int):
        super().__init__(transciever, source, sequence_number)
        self.value = value

    def __repr__(self):
        return super().__repr__() + " < {}".format(self.value)

class AddressedCommand(AddressedMessage):
    command: DaliCommandCode    

    def __init__(self, transciever: DaliBusTransciever, source: MessageSource, sequence_number: int, address: AbstractDaliAddress, command: DaliCommandCode):
        super().__init__(transciever, source, sequence_number, address)
        self.command = command

    def __repr__(self):
        return super().__repr__() + " > {}({})".format(self.command.name, self.address)

    @property
    def affected_gear(self):
        if self.command.has_side_effects:
            return super().affected_gear
        else:
            return []


class SpecialCommand(DaliMessage):
    command: SpecialCommandCode
    operand: int

    def __init__(self, transciever: DaliBusTransciever, source: MessageSource, sequence_number: int, command: SpecialCommandCode, operand: int):
        super().__init__(transciever, source, sequence_number)
        self.command = command
        self.operand = operand

    def __repr__(self):
        return super().__repr__() + " special > {}(0x{:02x})".format(self.command.name, self.operand)


class BadFrame(DaliMessage):
    def __repr__(self):
        return super.__repr__() + " Bad Frame"




