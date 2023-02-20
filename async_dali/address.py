from .types import DaliException

class AbstractDaliAddress:
    """Representation of an address of a message either sent or received by the bus.  Subclasses contain the real info"""
    @staticmethod
    def parse_address(addr_byte: int):
        if addr_byte == DaliBroadcastAddress.ALL or addr_byte == DaliBroadcastAddress.UNADDRESSED:
            return DaliBroadcastAddress()
        elif addr_byte & 0x80:
            if addr_byte & 0x60 != 0:
                raise DaliException("Invalid Group Address")  # Its a special addrss
            return DaliGearGroupAddress((addr_byte >> 1) & 0x0F)
        else:
            return DaliGearAddress(addr_byte >> 1)

    @property
    def code(self):
        raise DaliException("Not Implemented");

    def matches_gear(self, g):
        return False


class DaliGearAddress(AbstractDaliAddress):
    """A specific piece of gear - valid values 0--63 inclusive"""
    def __init__(self, addr):
        if addr < 0 or addr > 63:
            raise DaliException("short address out of bounds")

        self.short_code = addr

    def __repr__(self) -> str:
        return "A{}".format(self.short_code)

    @property
    def code(self):
        return self.short_code << 1

    def __eq__(self, o: object) -> bool:
        return isinstance(o, DaliGearAddress) and o.short_code == self.short_code

    def matches_gear(self, g):
        return g.address == self 

        

class DaliGearGroupAddress(AbstractDaliAddress):
    """A group of devices - valid values of 0--15 inclusive """
    def __init__(self, group):
        if group < 0 or group > 15:
            raise DaliException("Group number out of bounds")
        
        self.group_num = group

    def __repr__(self) -> str:
        return "G{}".format(self.group_num)

    @property
    def code(self):
        return self.group_num << 1 | 0x80

    def __eq__(self, o: object) -> bool:
        return isinstance(o, DaliGearGroupAddress) and o.group_num == self.group_num


    def matches_gear(self, g):
        return g.address == self or (g.groups & (1 << self.group_num) != 0)


class DaliBroadcastAddress(AbstractDaliAddress):
    """Addressed to all devices"""
    ALL = 0xFF
    UNADDRESSED = 0xFF

    def __init__(self, unaddressed=False):
        self.unaddressed = unaddressed

    @property
    def code(self):
        if self.unaddressed:
            return DaliBroadcastAddress.UNADDRESSED
        else:
            return DaliBroadcastAddress.ALL

    def __repr__(self) -> str:
        if self.unaddressed:
            return "Unaddressed Broadcast"
        else:
            return "Broadcast"

    def matches_gear(self, g):
        return True


