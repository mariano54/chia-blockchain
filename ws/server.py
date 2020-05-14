import asyncio

import aiohttp.web


async def async_main():
    routes = aiohttp.web.RouteTableDef()

    @routes.get('/')
    async def hello(request):
        breakpoint()
        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)

        await ws.send_bytes(b"hello there")
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                if msg.data == 'close':
                    await ws.close()
                else:
                    await ws.send_str(msg.data + '/answer')
            elif msg.type == aiohttp.WSMsgType.ERROR:
                pass

        return ws

    app = aiohttp.web.Application()
    app.add_routes(routes)
    await aiohttp.web._run_app(app)


def main():
    asyncio.get_event_loop().run_until_complete(async_main())


if __name__ == "__main__":
    main()
