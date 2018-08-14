import hashlib
import hmac
import threading
from abc import ABC, abstractmethod
from itertools import chain, repeat
from os import urandom
from time import sleep
from typing import Dict, Iterator, List, Type

from flask import Flask, request

from twlived.utils import Subscriber
from . import downloader
from .twitch import HubTopic, TwitchAPI
from .utils import BaseEvent, Publisher


class StreamUp(BaseEvent):
    stream_info: Dict


class StreamTracker(Publisher, Subscriber, ABC):
    events = [StreamUp]
    handle_events = [downloader.StartDownloading, downloader.StopDownloading]

    def __init__(self, twitch_api: TwitchAPI, channel: str):
        super().__init__()
        self._api = twitch_api
        self.channel = channel
        self.paused = False
        self._pre_init()
        self._thread = threading.Thread(target=self._process, daemon=True)
        self._post_init()

    @abstractmethod
    def _process(self):
        pass

    def _pre_init(self):
        pass

    def _post_init(self):
        pass


class CommonTracker(StreamTracker):
    def handle(self, event: BaseEvent) -> None:
        if isinstance(event, downloader.StartDownloading):
            self.paused = True
        elif isinstance(event, downloader.StopDownloading):
            self.paused = False

    def _process(self):
        delay = new_delay()
        while True:
            while not self.paused:
                stream_info = self._api.get_stream(self.channel)
                if stream_info:
                    self.publish(StreamUp(stream_info=stream_info))
                    delay = new_delay()

                waiting_time = next(delay)
                sleep(waiting_time)
            sleep(2)


class WebhookTracker(StreamTracker):
    STREAMS_HOOK = 'streams'

    def __init__(self, twitch_api: TwitchAPI, user_ids: List[str], hostname: str):
        super().__init__(twitch_api, user_ids)
        self._flask_app = Flask(self.__class__.__name__)
        self._webhook_secret = urandom(16)
        self.hostname = hostname

    def _process(self):
        # Run flask webhook server
        @self._flask_app.route(f'/{WebhookTracker.STREAMS_HOOK}', methods=['POST'])
        def streams_post():
            _, signature = request.headers.get('X-Hub-Signature', None).split('=')
            digest = hmac.new(self._webhook_secret, request.data, digestmod=hashlib.sha256)
            if not (signature and hmac.compare_digest(digest.hexdigest(), signature)):
                return '', 403
            self.publish(StreamUp(stream_info=request.json))
            return '', 200

        @self._flask_app.route(f'/{WebhookTracker.STREAMS_HOOK}', methods=['GET'])
        def streams_get():
            hub_mode = request.args.get('hub.mode')
            if hub_mode == 'denied':
                return '', 200
            elif hub_mode == 'subscribe' or hub_mode == 'unsubscribe':
                return request.args.get('hub.challenge'), 200
            else:
                return '', 400

        self._flask_app.run(debug=False)

    def _post_init(self):
        # Register the server to TwitchAPI via post_webhook
        callback_webhook = f'{self.hostname}/{WebhookTracker.STREAMS_HOOK}'
        for user_id in self.user_ids:
            self._api.post_webhook(callback_webhook, 'subscribe', HubTopic.streams(user_id),
                                   hub_secret=str(self._webhook_secret, encoding='ascii'))


def create_checker(cls: Type[StreamTracker], twitch_api: TwitchAPI, user_ids: List[str]):
    return cls(twitch_api, user_ids)


def delay_generator(maximum: int, step: int) -> Iterator[int]:
    return chain(range(step, maximum, step), repeat(maximum))


def new_delay() -> Iterator[int]:
    return delay_generator(900, 60)
