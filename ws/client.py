import asyncio

import aiohttp


async def async_main():
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect('http://127.0.0.1:8080/') as ws:
            breakpoint()
            await ws.send_bytes(b"hiya")
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    if msg.data == 'close cmd':
                        await ws.close()
                        break
                    else:
                        await ws.send_str(msg.data + '/answer')
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break


def main():
    asyncio.get_event_loop().run_until_complete(async_main())


if __name__ == "__main__":
    main()
