from async_dali import DaliBusTransciever
import asyncio
import logging
import sys


_LOGGER = logging.getLogger(__name__)

async def testit():
    await DaliBusTransciever.scan_for_transcievers()
    busses = DaliBusTransciever.transcievers
    if len(busses) == 0:
        raise Exception("No DALI transciever found")
    
    _LOGGER.info("Opening first discovered bus: %s", busses[0])
    async with busses[0] as bus:
        _LOGGER.info("Scanning for gear")
        await bus.scan_for_gear()
        gear = bus.present_gear

        if len(gear) == 0:
            raise Exception("No gear found on the bus")
        g = gear[0]
        _LOGGER.info("Blinking %s for 2 seconds", g.unique_id)

        # Toggle the light on then off again
        await g.on()
        await asyncio.sleep(2)
        await g.off()
    _LOGGER.info("Done")


if __name__ == "__main__":
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(testit())
    loop.close()
