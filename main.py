# encoding=utf-8
import logging.config
from time import sleep

import requests
from tenacity import retry, wait_fixed, stop_after_attempt
from tenacity import retry_if_exception_type as retry_on

import config
from network import request_get_retried
from storage import TwitchVideo, Storage
from telegram_bot import TelegramBot
from twitch_api import TwitchAPI, NoValidVideo
from view import View, ViewEvent

_config = config.init()
logging.config.dictConfig(_config['logging'])

channel = _config['main']['channel'].lower()
quality = TwitchAPI.VideoQuality.get(_config['main']['quality'])

_twitchAPI = TwitchAPI(client_id=_config['twitch']['client_id'],
                       fetch=request_get_retried)
_storage = Storage(storage_path=_config['storage']['path'],
                   vod_path_template=_config['storage']['vod_path'])
if _config['telegram']['enabled']:
    _bot = TelegramBot(token=_config['telegram']['api_token'], chat_id=_config['telegram']['chat_id'])
    _view = View(telegram_bot=_bot)
else:
    _view = View()


@retry(retry=retry_on(NoValidVideo), wait=wait_fixed(10), stop=stop_after_attempt(30))
def get_recording_video_info(channel_: str):
    return _twitchAPI.get_recording_video(channel_)


@retry(retry=retry_on(requests.ConnectionError), wait=wait_fixed(300))
def process():
    while True:
        _view(ViewEvent.CheckStatus, channel)
        if _twitchAPI.get_stream_status(channel) == 'online':
            _view(ViewEvent.WaitLiveVideo)
            stream_video = TwitchVideo(view=_view,
                                       info=get_recording_video_info(channel),
                                       api=_twitchAPI,
                                       quality=quality,
                                       temp_dir=_config['main']['temp_dir'])
            stream_video.download()
            _storage.add_broadcast(stream_video)
        _view(ViewEvent.WaitStream)
        sleep(300)


if __name__ == '__main__':
    process()
