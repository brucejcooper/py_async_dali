from async_dali import DaliBusTransciever
import asyncio

from async_dali import DaliGearGroup


async def testit():
    await DaliBusTransciever.scan_for_transcievers()
    busses = DaliBusTransciever.transcievers
    if len(busses) == 0:
        raise Exception("No DALI transciever found")
    
    print("Opening first discovered bus", busses[0])
    async with busses[0] as bus:
        print("Scanning for gear")
        gear = await bus.scan_for_gear()
        if len(gear) == 0:
            raise Exception("No gear found on the bus")

        group = bus.groups[2]

        # Toggle the group on then off again
        await group.on()
        await asyncio.sleep(0.1)
        lvl = await group.update_level()
        if lvl == 0:
            raise Exception("Expected group level to be on")
        await asyncio.sleep(2)

        await group.off()
        await asyncio.sleep(0.1)
        lvl = await group.update_level()
        if lvl != 0:
            raise Exception("Expected group level to be off")
    print("Done")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(testit())
    loop.close()
