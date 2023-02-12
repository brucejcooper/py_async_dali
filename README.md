This is a python package that facilitates reading from and control over a [DALI (IEC 62386)](https://www.dali-alliance.org/) protocol bus using a USB adapter such as the [Tridonic USB](https://www.tridonic.com/com/en/products/dali-usb.asp) adapter. 

The intention for this package is that it will be used to add DALI support to [Home Assistant](https://www.home-assistant.io/)



# Approach
DALI uses a short addressing scheme, assigning every device on the bus a number between 0 and 63 inclusive.  But these addresses can change if a re-address operation is performed.  Instead, when a device is created by this library, it determines a unique identifier by concatenating three pieces of information:

1. The Device [GTIN](https://www.gtin.info/)
2. The device's serial number
3. The logical enpoint number. A single device might house more than one gear endpoint. For example, a [Tridonic 4 channel relay](https://www.tridonic.com/com/en/products/DALI-RMS-4x10A.asp) advertises itself as 4 separate devices, but each one will have the same GTIN and serial number.

All of this information is loaded in from memory bank 0 of the device (see [this article](https://infosys.beckhoff.com/english.php?content=../content/1033/tcplclib_tc3_dali/6940982539.html&id=) for more details.).  The unique Id isn't particularly human readable, but it will remain static for the lifetime of that device.

when dealing with devices, you should always use the `unique_id` property to refer to devices.  That way they'll still work if a re-address is done or the device is moved to another bus.


# Usage
All useage starts with the Bus Transciever.  This is the component that interfaces to USB and will send/receive commands.  This class exclusively uses asyncio.

Drivers can be explicitly opened using the constructor, or scanned for using ```scan_for_dali_transcievers()``` which will return a list of all auto-discovered drivers. 

These drivers are also intended to pick up commands that are issued by other devices on the bus.  This is important to keep any visible state displayed to a user in sync with what has happened, without having to do a lot of polling (which will use up more power).  to listen to events on the bus, call `add_message_callback()` on the bus transciever.  However, if you just want to send commands and get responses back, you don't need to use the callback system. 


## Example

```py
from async_dali import TridonicDali
import asyncio


async def testit():
    busses = TridonicDali.scan_for_transcievers()
    if len(busses) == 0:
        raise Exception("No DALI transciever found")
    
    print("Opening first discovered bus", busses[0])
    async with busses[0] as bus:
        print("Scanning for gear")
        gear = await bus.scan_for_gear()

        if len(gear) == 0:
            raise Exception("No gear found on the bus")
        g = gear[0]
        print("Toggling", g.unique_id)

        # Toggle the light on then off again
        await g.on()
        await asyncio.sleep(2)
        await g.off()
    print("Done")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(testit())
    loop.close()
```