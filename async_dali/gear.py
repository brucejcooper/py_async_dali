from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple

from .dali_alliance_db import DaliAllianceProductDB, DaliAllianceProductRecord
from .types import DaliCommandCode, DaliException, SpecialCommandCode


class Fade(NamedTuple):
    """
    Fade rate
    1: 358 steps/sec
    2. 253 steps/sec
    3. 179 steps/sec
    4. 127
    5. 89 
    6. 63
    7. 45 
    8. 32
    9. 22
    10. 16
    11. 11.2
    12. 7.9
    13. 5.6
    14. 4.0
    15. 2.8
    """

    """
    Fade Time
    0: < 0.7sec
    1: 0.7
    2. 1
    3. 1.4
    4. 2 
    5. 2.8
    6. 4
    7. 5.6
    8. 8
    9. 11.3 
    10. 16
    11. 22.6
    12. 32
    13. 45.2
    14. 64
    15. 90.5 seconds

    """
    time: int
    rate: int


class GearType(Enum):
    FLOURESCENT_LAMP = 0
    EMERGENCY_LIGHTING = 1
    HID_LAMP = 2
    LOW_VOLTAGE_HALOGEN_LAMP = 3
    INCANDESCENT_LAMP_DIMMER = 4
    DC_CONTROLLED_DIMMER = 5
    LED_LAMP = 6
    RELAY = 7
    COLOUR = 8


@dataclass
class DaliGear:
    # The main fields that must be set at construction time.
    transciever: Any  # To avoid circular dependency
    address: int

    # Device state
    level: int = 0

    # Device info that we read from memory bank 0 - These won't be populated until fetch_deviceinfo is called
    device_type: GearType|None = None
    dalidb_record: DaliAllianceProductRecord|None = None
    last_mem_bank: int = 0
    gtin: int = 0
    firmware_version: str|None = None
    serial: str|None = None
    hardware_version: str|None = None
    dali_version: int = 0
    device_num_logical_control_units: int = 0
    device_num_logical_control_gears: int = 0
    device_control_index: int = 0

    @property
    def unique_id(self):
        """
        DALI defines the combination of GTIN and serial number to be globally unique and immutable, but
        a single physical device might consist of multiple logical devices, so we add that too
        """
        if self.device_type is None:
            raise DaliException("Device info not fetched")
        return "{}-{}-{}".format(self.gtin, self.serial, self.device_control_index)


    async def _send_cmd(self, cmd):
        return await self.transciever.send_cmd(self.address, cmd)

    async def read_memory(self, bank, offset, num):
        await self.transciever.send_special_cmd(SpecialCommandCode.SetDTR1, bank)  # Set memory bank
        await self.transciever.send_special_cmd(SpecialCommandCode.SetDTR0, offset)  # Set location 

        buf = bytearray()
        for i in range(num):
            b =  await self.transciever.send_cmd(self.address, DaliCommandCode.ReadMemoryLocation)
            if b is None:
                raise Exception("got no response when querying memory")
            buf.append(b)
        return bytes(buf)

    
    async def fetch_deviceinfo(self):
        dt = await self.transciever.send_cmd(self.address, DaliCommandCode.QueryDeviceType)
        if dt is None:
            self.device_type = None
        else:
            self.device_type = GearType(dt)
        if self.device_type is not None:
            # Read information on the bank 0 of the device
            # See https://infosys.beckhoff.com/english.php?content=../content/1033/tcplclib_tc3_dali/6940982539.html&id= for details on the memory banks
            # Returns the content of the memory location stored in DTR0 that is located within the memory bank listed in DTR1
            buf = await self.read_memory(0, 2, 25)

            '''
            Example DALI data (from index 02 onwards. )
            LMB GTIN        VER  SER Major  SER MI HWV  DALI VERSION
            01 07ee4bb3b889 0707 00001a5838 920269 0300 08 

            GTIN can be looked up by screen scraping 

            '''
            g0 = await self._send_cmd(DaliCommandCode.QueryGroupsZeroToSeven)
            g1 = await self._send_cmd(DaliCommandCode.QueryGroupsEightToFifteen)
            self.groups = g1 << 8 | g0

            self.min_level = await self._send_cmd(DaliCommandCode.QueryMinLevel)
            self.max_level = await self._send_cmd(DaliCommandCode.QueryMaxLevel)

            
            self.gtin = int.from_bytes(buf[1:7], "big")
            self.last_mem_bank = buf[0],
            self.firmware_version = "{}.{}".format(buf[7],buf[8]),
            self.serial = "{:02x}{:02x}{:02x}{:02x}{:02x}.{:02x}{:02x}{:02x}".format(buf[13],buf[12],buf[11],buf[10],buf[9],buf[16],buf[15],buf[14])
            self.hardware_version = "{}.{}".format(buf[17], buf[18]),
            self.dali_version = buf[19]

            self.device_num_logical_control_units = buf[22]
            self.device_num_logical_control_gears = buf[23]
            self.device_control_index = buf[24]

            with DaliAllianceProductDB() as db:
                self.dalidb_record = await db.fetch(self.gtin)
            await self.update_level()


    async def update_level(self): 
        self.level = await self._send_cmd(DaliCommandCode.QueryActualLevel)
        return self.level


    def matches_address(self, addr):
        """supplied with a dali address (bit shifted and with group marker), check to see if it addresses this entity"""
        if addr == 0xFF:
            return True
        if addr & 0x80:
            # Address is a group address.
            group_bm = 1 << (addr >> 1 & 0x0F)
            return self.groups & group_bm != 0
        else:
            return self.address == addr >> 1


    async def brightness(self, level):
        await self.transciever.send_direct_arc_power(self.address << 1, level)
        # self.level = level

    async def on(self):
        # For the LED ballasts I'm using, Sending the ON command doesn't seem to work.  Instead, we recall the last active level (could also be recall Max level)
        await self._send_cmd(DaliCommandCode.GoToLastActiveLevel)

    async def max(self):
        # For the LED ballasts I'm using, Sending the ON command doesn't seem to work.  Instead, we recall the last active level (could also be recall Max level)
        await self._send_cmd(DaliCommandCode.RecallMaxLevel)

    async def min(self):
        # For the LED ballasts I'm using, Sending the ON command doesn't seem to work.  Instead, we recall the last active level (could also be recall Max level)
        await self._send_cmd(DaliCommandCode.RecallMinLevel)


    async def query_fade(self):
        fade_and_rate =  await self._send_cmd(DaliCommandCode.QueryFadeTimeFadeRate)
        return Fade(time = fade_and_rate >> 4, rate = fade_and_rate & 0x0F)


    async def off(self):
        await self._send_cmd(DaliCommandCode.Off)

    async def brighten(self):
        await self._send_cmd(DaliCommandCode.Up)

    async def dim(self):
        await self._send_cmd(DaliCommandCode.Down)

    async def query_power_on_level(self):
        return await self._send_cmd(DaliCommandCode.QueryPowerOnLevel)

    async def set_power_on_level(self, level):
        await self.transciever.send_special_cmd(DaliCommandCode.SetDTR0, level)
        # Command must be sent twice within 100ms.
        await self._send_cmd(DaliCommandCode.SetPowerOnLevel)
        await self._send_cmd(DaliCommandCode.SetPowerOnLevel)


    async def toggle(self):
        level = await self.get_level()
        if level == 0:
            await self.on()
        else:
            await self.off()
