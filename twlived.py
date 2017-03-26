# encoding=utf-8
import logging.config
from time import sleep

import yaml
from tenacity import retry, retry_if_exception_type, wait_fixed

from storage import TwitchVideo, Storage
from twitchAPI import TwitchAPI, NoValidVideo
from view import View

# TODO добавить тесты
# TODO валидация конфига
with open('config.yaml', 'rt') as f:
    config = yaml.safe_load(f.read())
logging.config.dictConfig(config['logging'])

channel = config['main']['channel']
quality = TwitchAPI.VideoQuality.get(config['main']['quality'])

_twitchAPI = TwitchAPI(client_id=config['twitch']['client_id'])
_storage = Storage(path=config['storage']['path'],
                   broadcast_path=config['storage']['vod_path'])
_view = View()


@retry(retry=retry_if_exception_type(NoValidVideo), wait=wait_fixed(2))
def get_recording_video_info(channel_: str):
    return _twitchAPI.get_recording_video(channel_)


while True:
    if _twitchAPI.get_stream_status(channel) == 'online':
        video_info = get_recording_video_info(channel)
        playlist_uri = _twitchAPI.get_video_playlist_uri(_id=video_info['_id'], quality=quality)
        stream_video: TwitchVideo = TwitchVideo(info=video_info,
                                                playlist_uri=playlist_uri,
                                                temp_dir=config['main']['temp_dir'])
        stream_video.download()
        _storage.add_broadcast(stream_video)
    print('waiting 300 sec')
    sleep(300)
