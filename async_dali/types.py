"""Types used by this module"""
from enum import Enum
from typing import Any, Generic, List, NamedTuple, TypeVar


class DaliException(Exception):
    """Dali Exception"""

class FramingException(DaliException):
    """Thrown when waiting for a response and a framing error occurrs (usually caused when two devices transmit at the same time)"""


class SearchAddressClashException(DaliException):
    """Thrown during provisioning if two gears choose the same search address"""


class DaliCommandCode(Enum):
    """ List of commands taken from https://onlinedocs.microchip.com/pr/GUID-0CDBB4BA-5972-4F58-98B2-3F0408F3E10B-en-US-1/index.html?GUID-DA5EBBA5-6A56-4135-AF78-FB1F780EF475"""
    Off = 0x00
    Up = 0x01
    Down = 0x02
    StepUp = 0x03
    StepDown = 0x04
    RecallMaxLevel = 0x05
    RecallMinLevel = 0x06
    StepDownAndOff = 0x07
    OnAndStepUp = 0x08
    EnableDAPCSequence = 0x09
    GoToLastActiveLevel = 0x0a
    ContinuousUp = 0x0b
    ContinuousDown = 0x0c
    GoToScene = 0x10
    Reset = 0x20
    StoreActualLevelInDTR0 = 0x21
    SavePersistentVariables = 0x22
    SetOperatingMode = 0x23
    ResetMemoryBank = 0x24
    IdentifyDevice = 0x25
    SetMaxLevel = 0x2a
    SetMinLevel = 0x2b
    SetSystemFailureLevel = 0x2c
    SetPowerOnLevel = 0x2d
    SetFadeTime = 0x2e
    SetFadeRate = 0x2f
    SetExtendedFadeTime = 0x30
    SetScene = 0x40
    RemoveFromScene = 0x50
    AddToGroup = 0x60
    RemoveFromGroup = 0x70
    SetShortAddress = 0x80
    EnableWriteMemory = 0x81
    QueryStatus = 0x90
    QueryControlGearPresent = 0x91
    QueryLampFailure = 0x92
    QueryLampPowerOn = 0x93
    QueryLimitError = 0x94
    QueryResetState = 0x95
    QueryMissingShortAddress = 0x96
    QueryVersionNumber = 0x97
    QueryContentDTR0 = 0x98
    QueryDeviceType = 0x99
    QueryPhysicalMinimum = 0x9a
    QueryPowerFailure = 0x9b
    QueryContentDTR1 = 0x9c
    QueryContentDTR2 = 0x9d
    QueryOperatingMode = 0x9e
    QueryLightSourceType = 0x9f
    QueryActualLevel = 0xa0
    QueryMaxLevel = 0xa1
    QueryMinLevel = 0xa2
    QueryPowerOnLevel = 0xa3
    QuerySystemFailureLevel = 0xa4
    QueryFadeTimeFadeRate = 0xa5
    QueryManufacturerSpecificMode = 0xa6
    QueryNextDeviceType = 0xa7
    QueryExtendedFadeTime = 0xa8
    QueryControlGearFailure = 0xaa
    QuerySceneLevel = 0xb0
    QueryGroupsZeroToSeven = 0xc0
    QueryGroupsEightToFifteen = 0xc1
    QueryRandomAddressH = 0xc2
    QueryRandomAddressM = 0xc3
    QueryRandomAddressL = 0xc4
    ReadMemoryLocation = 0xc5


    @property
    def has_side_effects(self):
        return self.value <= DaliCommandCode.Reset.value



class SpecialCommandCode(Enum):
    Terminate = 0xa1
    Initialise = 0xA5
    Randomise = 0xa7
    Compare = 0xa9
    Withdraw = 0xab
    Ping = 0xad
    SearchAddrH = 0xb1
    SearchAddrM = 0xb3
    SearchAddrL = 0xb5
    ProgramShortAddress = 0xb7
    VerifyShortAddress = 0xb9
    QueryShortAddress = 0xbb
    EnableDeviceType = 0xc1
    SetDTR0 = 0xa3
    SetDTR1 = 0xc3
    SetDTR2 = 0xc5
    WriteMemoryLocation = 0xc7
    WriteMemoryLocationNoReply = 0xc9

    @staticmethod
    def is_special_command(addr_byte: int) -> bool:
        return addr_byte & 0x80 == 0x80 and addr_byte & 0x60 != 0


class MessageSource(Enum):
    EXTERNAL = 0x11
    SELF = 0x12
    SENT = 0x13  # I added this, but I can't remember why.




T = TypeVar('T')

class ItemDelta(Generic[T]):
    """When scanning we want to know what was added and removed.  This presents a generic result of a scan"""
    added: List[T]
    removed: List[T]

    def __init__(self, added: List[T], removed: List[T]) -> None:
        self.added = added
        self.removed = removed

    def __repr__(self) -> str:
        return "Delta(added: {}, removed: {})".format(self.added, self.removed)

    def extend(self, d: 'ItemDelta'):
        """Extends this delta with another delta - Note: this does not deal with duplicates"""
        self.added.extend(d.added)
        self.removed.extend(d.removed)
