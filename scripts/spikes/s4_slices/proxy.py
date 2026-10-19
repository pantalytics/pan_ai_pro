"""Route /websocket to Odoo's gevent worker (8072) and everything else to the
HTTP workers (8069), as Caddy or nginx would in production. Needed for a
prefork server (workers > 0), which is what the time limits apply to.

    python proxy.py 8080
"""
import asyncio
import sys

LISTEN = int(sys.argv[1]) if len(sys.argv) > 1 else 8080


async def pipe(r, w):
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def handle(reader, writer):
    head = await reader.read(65536)
    port = 8072 if head.startswith(b"GET /websocket") else 8069
    try:
        ur, uw = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        writer.close()
        return
    uw.write(head)
    await uw.drain()
    await asyncio.gather(pipe(reader, uw), pipe(ur, writer))


async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", LISTEN)
    async with server:
        await server.serve_forever()


asyncio.run(main())
