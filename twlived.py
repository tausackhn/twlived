# encoding=utf-8
from time import sleep

import twitch_video
from storage import Storage
from twitchAPI import TwitchAPI
from view import View

channel = 'bulbazabp'
quality = 'Source'

_twitchAPI = TwitchAPI(headers={'Accept': 'application/vnd.twitchtv.v3+json',
                                'Client-ID': '1jjwhjqteoa0tc75bhvm251wiqpar80'})
_storage = Storage(path='C:/mydir')
_view = View()

while True:
    if _twitchAPI.get_stream_status(channel) == 'online':
        stream_playlist_uri: str = _twitchAPI.get_stream_playlist_uri(channel, quality)
        broadcast: twitch_video.TwitchVideo = twitch_video.download_from(stream_playlist_uri)
        _storage.add_broadcast(broadcast)
    else:
        print('waiting 120 sec')
        sleep(120)
# test = _twitchAPI.get_stream_playlist_uri(channel, quality)
# print(test)
