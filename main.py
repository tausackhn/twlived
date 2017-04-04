# encoding=utf-8
import logging.config
from time import sleep

from tenacity import retry, retry_if_exception_type, wait_fixed

import config
from storage import TwitchVideo, Storage
from twitchAPI import TwitchAPI, NoValidVideo

_config = config.init()
logging.config.dictConfig(_config['logging'])

channel = _config['main']['channel']
quality = TwitchAPI.VideoQuality.get(_config['main']['quality'])

_twitchAPI = TwitchAPI(client_id=_config['twitch']['client_id'])
_storage = Storage(storage_path=_config['storage']['path'],
                   vod_path_template=_config['storage']['vod_path'])


@retry(retry=retry_if_exception_type(NoValidVideo), wait=wait_fixed(2))
def get_recording_video_info(channel_: str):
    return _twitchAPI.get_recording_video(channel_)


while True:
    if _twitchAPI.get_stream_status(channel) == 'online':
        video_info = get_recording_video_info(channel)
        playlist_uri = _twitchAPI.get_video_playlist_uri(_id=video_info['_id'], quality=quality)
        stream_video: TwitchVideo = TwitchVideo(info=video_info,
                                                playlist_uri=playlist_uri,
                                                temp_dir=_config['main']['temp_dir'])
        stream_video.download()
        _storage.add_broadcast(stream_video)
    print('waiting 300 sec')
    sleep(300)
