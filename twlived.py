# encoding=utf-8
import logging
from time import sleep

from tenacity import retry, retry_if_exception_type, wait_fixed

from storage import TwitchVideo, Storage
from twitchAPI import TwitchAPI, NoValidVideo
from view import View

logging.basicConfig(filename='twlived.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logging.getLogger().addHandler(logging.StreamHandler())

channel = 'guit88man'
quality = TwitchAPI.VideoQuality.SOURCE

_twitchAPI = TwitchAPI(client_id='qxwnp14rr4y6l0pqpfmj6s384079n7')
_storage = Storage(path='D:/vods')
_view = View()


@retry(retry=retry_if_exception_type(NoValidVideo), wait=wait_fixed(2))
def get_recording_video_info(channel_: str):
    return _twitchAPI.get_recording_video(channel_)


while True:
    if _twitchAPI.get_stream_status(channel) == 'online':
        video_info = get_recording_video_info(channel)
        playlist_uri = _twitchAPI.get_video_playlist_uri(_id=video_info['_id'], quality=quality)
        stream_video: TwitchVideo = TwitchVideo(info=video_info, playlist_uri=playlist_uri)
        stream_video.download()
        _storage.add_broadcast(stream_video)
    print('waiting 120 sec')
    sleep(120)
