import asyncio
import logging
import os

from dotenv import find_dotenv, load_dotenv

from twlived import RegularTracker, TwitchAPI
from twlived.utils import BaseEvent, Provider, Subscriber

load_dotenv(find_dotenv())
CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')
if not CLIENT_ID:
    raise ValueError('CLIENT_ID not found in environment variables')

logging.basicConfig(level=logging.DEBUG)


class SimpleView(Subscriber):
    async def handle(self, event) -> None:
        print(event)


async def stop_after(tracker, time):
    await asyncio.sleep(time)
    await tracker.stop()


async def main():
    async with TwitchAPI(CLIENT_ID, client_secret=CLIENT_SECRET, version='Helix') as api:
        streams = await api.get_api('Helix').get_streams(first=40)
        users = await api.get_api('Helix').get_users(id=[stream['user_id'] for stream in streams.data])
        channels = ([user['login'] for user in users]
                    # Non-existent channels
                    + ['a', 'b']
                    # Add your favorite channels
                    + [])

        message_center = Provider()
        all_events_printer = SimpleView()
        tracker = RegularTracker(channels, api, poll_period=15)
        message_center.connect(all_events_printer, tracker)
        all_events_printer.subscribe(BaseEvent)

        time = 3600
        asyncio.create_task(stop_after(tracker, time))

        await tracker.run()


asyncio.run(main())
