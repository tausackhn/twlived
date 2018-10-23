import asyncio
import logging
import os
from pathlib import Path

import aiohttp
from dotenv import find_dotenv, load_dotenv

from twlived import ProgressData, RegularTracker, StreamOnline, StreamType, TwitchAPI, TwitchStreamDownloader
from twlived.utils import BaseEvent, Provider, Subscriber

logging.basicConfig(level=logging.DEBUG)

load_dotenv(find_dotenv())
CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
if not CLIENT_ID:
    raise ValueError('CLIENT_ID not found in environment variables')


class SimpleView(Subscriber):
    async def handle(self, event) -> None:
        print(event)


class Progress:
    def __init__(self, first_segment=0, last_segment=0, completed_size=0):
        self.first_segment = first_segment
        self.last_segment = last_segment
        self.completed_size = completed_size
        self.total_jobs = 0
        self.completed_jobs = 0
        self.written_segments = 0

    def update(self, data: ProgressData):
        if data.first_segment:
            self.first_segment = data.first_segment
        if data.last_segment:
            self.last_segment = data.last_segment
            self.total_jobs = self.last_segment - self.first_segment + 1
        if data.data_size:
            self.completed_size += data.data_size
        if data.complete_segment:
            self.completed_jobs += 1
        if data.write_segment:
            self.written_segments += 1

    async def periodic_print(self):
        while True:
            print(self)
            await asyncio.sleep(1)

    def __str__(self):
        return (f'First segment: {self.first_segment:5}; Last segment: {self.last_segment:5}'
                f' Downloaded segments: {self.completed_jobs:5}/{self.total_jobs:5}'
                f' Written segments: {self.written_segments}'
                f' Total size: {self.completed_size}B')


async def main():
    async with aiohttp.ClientSession() as session, TwitchAPI(CLIENT_ID) as api:
        channels = ['eligorko']
        tracker = RegularTracker(channels, api)
        stream_download_manager = TwitchStreamDownloader(api,
                                                         session=session,
                                                         stream_type=StreamType.LIVE,
                                                         temporary_folder=Path('.'))

        message_center = Provider()
        simple_handler = SimpleView()
        message_center.connect(tracker, simple_handler, stream_download_manager)
        simple_handler.subscribe(BaseEvent)
        # If subscribe StreamOnline and StreamChanged together stream_download_manager handles StreamOnline event twice
        # because StreamOnline is subclass of StreamChanged
        stream_download_manager.subscribe(StreamOnline)

        progress = Progress()

        stream_download_manager.manager.progress_callback = progress.update
        asyncio.create_task(progress.periodic_print())

        await tracker.run()


asyncio.run(main())
