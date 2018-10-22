import asyncio
import hashlib
import hmac
from base64 import b64encode
from collections import deque
from functools import wraps
from os import urandom
from typing import Awaitable, Callable, Deque, Dict, List, Optional, TypeVar, cast

from aiohttp import web

from .base import CONNECTION_ERRORS, StreamTrackerBase
from ..twitch import HelixData, HubTopic, StreamInfo, TwitchAPI, TwitchAPIHelix
from ..twitch.adapters import prepare_stream_info
from ..utils import retry_on_exception

T = TypeVar('T')
WebhookTrackerMethod = Callable[['WebhookTracker', web.Request], Awaitable[web.Response]]


def validate_channel(coro: WebhookTrackerMethod) -> WebhookTrackerMethod:
    @wraps(coro)
    async def wrapper(self: 'WebhookTracker', request: web.Request) -> web.Response:
        channel = request.match_info['channel']
        if channel not in self.channels:
            return web.Response(status=400)

        return await coro(self, request)

    return wrapper


class WebhookTracker(StreamTrackerBase):
    STREAMS = 'streams'
    WEBHOOK_BASE = 'helix/webhook'

    def __init__(self, channels: List[str], twitch_api: TwitchAPI, host: str, *,
                 port: int = 22881, lease_time: int = 86400) -> None:
        super().__init__(channels)
        self.api = cast(TwitchAPIHelix, twitch_api.get_api('Helix'))
        self.host = host
        self.port = port
        self._lease_time = lease_time

        # channel: 'subscribed', 'unsubscribed' or None (channel has not found on Twitch.TV)
        self._subscription_statuses: Dict[str, Optional[str]] = {channel: None for channel in self.channels}

        # Need for firing only unique events
        self._event_ids: Deque[str] = deque(maxlen=100)

        self.app = web.Application()
        self.app.add_routes([
            web.get(f'/{WebhookTracker.WEBHOOK_BASE}/{WebhookTracker.STREAMS}/{{channel}}', self.on_streams_get),
            web.post(f'/{WebhookTracker.WEBHOOK_BASE}/{WebhookTracker.STREAMS}/{{channel}}', self.on_streams_post),
        ])
        self.webhook_secret = b64encode(urandom(16))

        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._webhook_register_task: Optional[asyncio.Task] = None

    async def run(self) -> None:
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, port=self.port)
        await self._site.start()
        self._auto_update_webhook()

        self._is_running = True
        # TODO: more suitable way?
        while self.is_running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        if self.is_running:
            if not self._runner:
                raise ValueError('No running site')
            await self._runner.cleanup()
            await self._unregister_webhooks()
            self._is_running = False

    def already_published(self, event_id: str) -> bool:
        return event_id in self._event_ids

    @validate_channel
    async def on_streams_post(self, request: web.Request) -> web.Response:
        # More info: https://dev.twitch.tv/docs/api/webhooks-reference/#subscribe-tounsubscribe-from-events
        # hub.secret
        _, signature = request.headers.get('X-Hub-Signature', None).split('=')
        data = await request.read()
        digest = hmac.new(self.webhook_secret, data, digestmod=hashlib.sha256)
        if not (signature and hmac.compare_digest(digest.hexdigest(), signature)):
            return web.Response(status=403)

        event_id = request.headers.get('Twitch-Notification-Id', None)
        if not event_id:
            return web.Response(status=404)

        if not self.already_published(event_id):
            stream_data = HelixData.from_json(await request.json())
            stream_info = cast(StreamInfo, await prepare_stream_info(self.api, stream_data)) if stream_data else None
            await self.stream_info_to_event(request.match_info['channel'], stream_info)

        return web.Response()

    @validate_channel
    async def on_streams_get(self, request: web.Request) -> web.Response:
        # More info: https://dev.twitch.tv/docs/api/webhooks-guide/#subscriptions
        hub_mode = request.query.get('hub.mode', None)
        if hub_mode == 'denied':
            return web.Response()
        elif hub_mode in {'subscribe', 'unsubscribe'}:
            self._subscription_statuses[request.match_info['channel']] = f'{hub_mode}d'
            return web.Response(text=request.query['hub.challenge'], status=200)
        return web.Response(status=400)

    async def _register_webhooks(self) -> None:
        @retry_on_exception(*CONNECTION_ERRORS, wait=10, max_tries=10)
        async def subscribe_webhook(webhook_url: str, topic: str, secret: str, lease_time: int) -> None:
            await self.api.post_webhook(webhook_url, 'subscribe', topic,
                                        hub_secret=secret,
                                        hub_lease_seconds=lease_time)

        user_data = await self.api.get_users(login=self.channels)
        tasks = []
        for user in user_data:
            webhook_path = (f'http://{self.host}:{self.port}'
                            f'/{WebhookTracker.WEBHOOK_BASE}/{WebhookTracker.STREAMS}/{user["login"]}')
            task = asyncio.create_task(subscribe_webhook(webhook_path, HubTopic.streams(user['id']),
                                                         str(self.webhook_secret, encoding='ascii'),
                                                         self._lease_time))
            tasks.append(task)
        await asyncio.wait(tasks)

    async def _unregister_webhooks(self) -> None:
        @retry_on_exception(*CONNECTION_ERRORS, wait=10, max_tries=10)
        async def unsubscribe_webhook(webhook_url: str, topic: str, secret: str, lease_time: int) -> None:
            await self.api.post_webhook(webhook_url, 'unsubscribe', topic,
                                        hub_secret=secret,
                                        hub_lease_seconds=lease_time)

        user_data = await self.api.get_users(login=[channel
                                                    for channel, status in self._subscription_statuses.items()
                                                    if status == 'subscribed'])
        tasks = []
        for user in user_data:
            webhook_path = (f'http://{self.host}:{self.port}'
                            f'/{WebhookTracker.WEBHOOK_BASE}/{WebhookTracker.STREAMS}/{user["login"]}')
            task = asyncio.create_task(unsubscribe_webhook(webhook_path, HubTopic.streams(user['id']),
                                                           str(self.webhook_secret, encoding='ascii'),
                                                           self._lease_time))
            tasks.append(task)
        await asyncio.wait(tasks)

    async def _update_webhook(self) -> None:
        while True:
            await self._register_webhooks()
            await asyncio.sleep(self._lease_time)

    def _auto_update_webhook(self) -> None:
        def callback(t: asyncio.Task) -> None:
            # noinspection PyBroadException
            try:
                t.result()
            except asyncio.CancelledError:
                pass

        self._webhook_register_task = asyncio.create_task(self._update_webhook())
        self._webhook_register_task.add_done_callback(callback)
