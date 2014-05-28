from __future__ import absolute_import

from kombu.common import ignore_errors
from kombu.utils.encoding import safe_str

from celery.datastructures import AttributeDict
from celery.utils.log import get_logger

from . import control

__all__ = ['Pidbox']

logger = get_logger(__name__)
debug, error, info = logger.debug, logger.error, logger.info


class Pidbox(object):
    consumer = None

    def __init__(self, c):
        self.c = c
        self.hostname = c.hostname
        self.node = c.app.control.mailbox.Node(
            safe_str(c.hostname),
            handlers=control.Panel.data,
            state=AttributeDict(app=c.app, hostname=c.hostname, consumer=c),
        )
        self._forward_clock = self.c.app.clock.forward

    def on_message(self, body, message):
        self._forward_clock()  # just increase clock as clients usually don't
                               # have a valid clock to adjust with.
        try:
            self.node.handle_message(body, message)
        except KeyError as exc:
            error('No such control command: %s', exc)
        except Exception as exc:
            error('Control command error: %r', exc, exc_info=True)
            self.reset()

    def start(self, c):
        self.node.channel = c.connection.channel()
        self.consumer = self.node.listen(callback=self.on_message)
        self.consumer.on_decode_error = c.on_decode_error

    def on_stop(self):
        pass

    def stop(self, c):
        self.on_stop()
        self.consumer = self._close_channel(c)

    def reset(self):
        """Sets up the process mailbox."""
        self.stop(self.c)
        self.start(self.c)

    def _close_channel(self, c):
        if self.node and self.node.channel:
            ignore_errors(c, self.node.channel.close)

    def shutdown(self, c):
        self.on_stop()
        if self.consumer:
            debug('Cancelling broadcast consumer...')
            ignore_errors(c, self.consumer.cancel)
        self.stop(self.c)
