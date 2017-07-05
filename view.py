from enum import Enum, auto

from telegram_bot import TelegramBot


class ViewEvent(Enum):
    CheckStatus = auto()
    WaitLiveVideo = auto()
    StartDownloading = auto()
    ProgressInfo = auto()
    StopDownloading = auto()
    MovingFile = auto()
    WaitStream = auto()


class View:
    def __init__(self, telegram_bot: TelegramBot = None):
        self._bot = telegram_bot

    def __call__(self, event: ViewEvent, info=None):
        if event is ViewEvent.CheckStatus:
            print(f'Looking for stream on {info}')
        elif event is ViewEvent.WaitLiveVideo:
            print('Looking for recording video')
        elif event is ViewEvent.StartDownloading:
            if self._bot:
                self._bot.send_message(f'Start downloading {info.id} on {info.channel}')
        elif event is ViewEvent.ProgressInfo:
            print(f"\rLast: {info.completed_segments:>5}/{info.segments:>5}  "
                  f"Total: {info.total_completed_segments:>5}/{info.total_segments:>5}", end='')
        elif event is ViewEvent.StopDownloading:
            if self._bot:
                self._bot.send_message('Downloading successfully')
        elif event is ViewEvent.MovingFile:
            pass
        elif event is ViewEvent.WaitStream:
            print('No live stream. Waiting 300 sec')
