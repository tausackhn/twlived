# encoding=utf-8
import logging.config
from time import sleep

import requests
from tenacity import retry, wait_fixed, stop_after_attempt
from tenacity import retry_if_exception_type as retry_on

import config
from storage import TwitchVideo, Storage
from twitch_api import TwitchAPI, NoValidVideo

_config = config.init()
logging.config.dictConfig(_config['logging'])

channel = _config['main']['channel']
quality = TwitchAPI.VideoQuality.get(_config['main']['quality'])

_twitchAPI = TwitchAPI(client_id=_config['twitch']['client_id'])
_storage = Storage(storage_path=_config['storage']['path'],
                   vod_path_template=_config['storage']['vod_path'])


@retry(retry=(retry_on(NoValidVideo) | retry_on(requests.HTTPError)),
       wait=wait_fixed(10),
       stop=stop_after_attempt(30))
def get_recording_video_info(channel_: str):
    return _twitchAPI.get_recording_video(channel_)


@retry(retry=(retry_on(requests.ConnectionError) | retry_on(requests.HTTPError)), wait=wait_fixed(2))
def process():
    while True:
        print(f'Looking for stream on {channel}')
        if _twitchAPI.get_stream_status(channel) == 'online':
            print('Looking for recording video')
            stream_video = TwitchVideo(info=get_recording_video_info(channel),
                                       api=_twitchAPI,
                                       quality=quality,
                                       temp_dir=_config['main']['temp_dir'])
            stream_video.download()
            _storage.add_broadcast(stream_video)
        print('No live stream. Waiting 300 sec')
        sleep(300)


if __name__ == '__main__':
    process()
