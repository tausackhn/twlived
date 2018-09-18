import logging
from datetime import timedelta
from itertools import repeat, chain
from time import sleep
from typing import Dict, Iterator

import requests
from iso8601 import parse_date

from .downloader import TwitchDownloadManager
from .events import CheckStatus, WaitLiveVideo, WaitStream, ExceptionEvent
from .storage import Storage
from .twitch_api import TwitchAPI
from .utils import retry_on_exception, Publisher

log = logging.getLogger(__name__)


def is_video_from_stream(video: Dict[str, str], stream: Dict[str, str]) -> bool:
    # Time between creating VOD and starting stream less than 2 minutes
    return bool(parse_date(video['created_at']) - parse_date(stream['started_at']) < timedelta(minutes=2))


def delay_generator(maximum: int, step: int) -> Iterator[int]:
    return chain(range(step, maximum, step), repeat(maximum))


def new_delay() -> Iterator[int]:
    return delay_generator(900, 60)


@retry_on_exception(requests.exceptions.RequestException)
def main(channel: str, quality: str, main_publisher: Publisher, twitch_api: TwitchAPI,
         download_manager: TwitchDownloadManager, storage: Storage) -> None:
    # noinspection PyBroadException,PyPep8
    try:
        delay = new_delay()
        while True:
            main_publisher.publish(CheckStatus(channel=channel))
            streams_info, _ = twitch_api.get_streams(user_login=[channel], type='live')
            if streams_info:
                stream_info = streams_info[0]
                if not stream_info['type'] == 'live':
                    continue
                main_publisher.publish(WaitLiveVideo())
                videos_info, _ = twitch_api.get_videos(user_id=stream_info['user_id'], type='archive')
                # Select the latest video
                video_info = next((video for video in videos_info if is_video_from_stream(video, stream_info)), None)
                if (video_info and
                        # Doesn't downloaded yet
                        video_info['id'] not in storage.added_broadcast_ids(video_info['type'])):
                    video, path = download_manager.download(video_info['id'],
                                                            quality=quality,
                                                            video_type=video_info['type'])
                    # `exist_ok=True` Possible if there have been a network problem.
                    storage.add_broadcast(video, path, exist_ok=True)
                    delay = new_delay()
            waiting_time = next(delay)
            main_publisher.publish(WaitStream(time=waiting_time))
            sleep(waiting_time)
    except KeyboardInterrupt:
        pass
    except:  # noqa
        main_publisher.publish(ExceptionEvent(message='Fatal error occurred. twLiveD was down.'))
        log.exception('Fatal error')
