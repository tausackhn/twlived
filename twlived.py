# encoding=utf-8
from time import sleep

from tenacity import retry, retry_if_exception_type, wait_fixed

from storage import TwitchVideo, Storage
from twitchAPI import TwitchAPI, NoValidVideo
from view import View

channel = 'kosdff'
quality = 'Source'

_twitchAPI = TwitchAPI(headers={'Accept': 'application/vnd.twitchtv.v3+json',
                                'Client-ID': '1jjwhjqteoa0tc75bhvm251wiqpar80'})
_storage = Storage(path='C:/mydir')
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
    else:
        print('waiting 120 sec')
        sleep(120)
# test = _twitchAPI.get_video_playlist_uri(channel, quality)
# print(test)
