# encoding=utf-8

from twitch_video import TwitchVideo


class Storage:
    def __init__(self, path='.'):
        self.path = path

    def add_broadcast(self, broadcast: TwitchVideo):
        pass
