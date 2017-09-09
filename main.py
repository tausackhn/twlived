from time import sleep
from typing import Dict, Generator, List

from requests import ConnectionError  # pylint: disable=redefined-builtin
from tenacity import retry, wait_fixed, stop_after_attempt  # type: ignore
from tenacity import retry_if_exception_type as retry_on

import config
from config_logging import setup_logging, LOG
from network import request_get_retried
from storage import TwitchVideo, Storage
from telegram_bot import TelegramBot
from twitch_api import TwitchAPI, NoValidVideo
from view import View, ViewEvent

setup_logging()
logger = LOG.getChild(__name__)  # pylint: disable=invalid-name

_config = config.init()
channel = _config['main']['channel'].lower()
quality = TwitchAPI.VideoQuality.get(_config['main']['quality'])
_twitchAPI = TwitchAPI(client_id=_config['twitch']['client_id'],
                       fetch=request_get_retried)
_storage = Storage(storage_path=_config['storage']['path'],
                   vod_path_template=_config['storage']['vod_path'])
if _config['telegram']['enabled']:
    _bot = TelegramBot(token=_config['telegram']['api_token'],
                       chat_id=_config['telegram']['chat_id'])
    _view = View(telegram_bot=_bot)
else:
    _view = View()


def delay_generator(maximum: int, step: int) -> Generator[int, int, None]:
    i = step
    while True:
        while i <= maximum:
            value = (yield i)
            if value is not None:
                i = value
            else:
                i += step
        while True:
            value = (yield maximum)
            if value is not None:
                i = value
                break


@retry(retry=retry_on(NoValidVideo), wait=wait_fixed(10), stop=stop_after_attempt(30), reraise=True)
def get_recording_videos_info(channel_: str) -> List[Dict]:
    return _twitchAPI.get_recording_videos(channel_)


@retry(retry=retry_on(ConnectionError), wait=wait_fixed(300))
def process() -> None:
    delay = delay_generator(900, 60)
    while True:
        _view(ViewEvent.CheckStatus, info=channel)
        if _twitchAPI.get_stream_status(channel) == 'online':
            _view(ViewEvent.WaitLiveVideo)
            try:
                for video_info in get_recording_videos_info(channel):
                    stream_video = TwitchVideo(view=_view,
                                               info=video_info,
                                               api=_twitchAPI,
                                               quality=quality,
                                               temp_dir=_config['main']['temp_dir'])
                    if stream_video.id != _storage.last_added_id:
                        stream_video.download()
                        _storage.add_broadcast(stream_video)
                        delay.send(0)
            # VOD obtain status `recording` before stream API changed status to `offline`
            except NoValidVideo:
                pass
        waiting_time = next(delay)
        _view(ViewEvent.WaitStream, info=waiting_time)
        sleep(waiting_time)


if __name__ == '__main__':
    # noinspection PyBroadException
    try:
        process()
    except KeyboardInterrupt:
        pass
    except:  # pylint: disable=bare-except
        logger.exception("Fatal error.")
