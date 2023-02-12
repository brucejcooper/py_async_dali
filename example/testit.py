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
