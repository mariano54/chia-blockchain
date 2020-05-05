import asyncio
import logging
import struct

from aiter import map_aiter, join_aiters

import cbor2

log = logging.getLogger(__name__)


async def reader_to_cbor_stream(reader):
    """
    Turn a reader into a generator that yields cbor messages.
    """
    while True:
        try:
            message_size_blob = await reader.readexactly(4)
            message_size, = struct.unpack(">L", message_size_blob)
            blob = await reader.readexactly(message_size)
            message = cbor2.loads(blob)
            log.debug("got msg %s", message)
            yield message
        except (IOError, asyncio.IncompleteReadError):
            log.info("EOF stream %s", reader)
            break
        except ValueError:
            log.info("badly formatted cbor from stream %s", reader)
            break
        except Exception:
            log.exception("unknown error in stream %s", reader)
            break


def transform_to_streamable(d):
    """
    Drill down through dictionaries and lists and transform objects with "bytes()" to bytes.
    """
    if hasattr(d, "__bytes__"):
        return bytes(d)
    if d is None or isinstance(d, (str, bytes, int)):
        return d
    if isinstance(d, dict):
        new_d = {}
        for k, v in d.items():
            new_d[transform_to_streamable(k)] = transform_to_streamable(v)
        return new_d
    return [transform_to_streamable(_) for _ in d]


def xform_to_cbor_message(msg):
    msg_blob = cbor2.dumps(transform_to_streamable(msg))
    length_blob = struct.pack(">L", len(msg_blob))
    return length_blob + msg_blob


def message_stream_to_event_stream(event_template, message_stream):
    """
    This tweaks each message from message_stream by wrapping it with a dictionary
    populated with the given template, putting the message is at the top
    level under "message".
    """

    template = dict(event_template)

    def adaptor(message):
        event = dict(template)
        event.update(message=message)
        return event

    return map_aiter(adaptor, message_stream)


def rws_to_event_aiter(rws_aiter, reader_to_message_stream):

    def rws_to_reader_event_template_adaptor(rws):
        return rws, rws["reader"]

    def reader_event_template_to_event_stream_adaptor(rws_reader):
        rws, reader = rws_reader
        return message_stream_to_event_stream(rws, reader_to_message_stream(reader))

    def adaptor(rws):
        return reader_event_template_to_event_stream_adaptor(
            rws_to_reader_event_template_adaptor(rws))

    return join_aiters(map_aiter(adaptor, rws_aiter))
