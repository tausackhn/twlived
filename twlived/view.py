import requests

from .events import CheckStatus, WaitLiveVideo, WaitStream, StartDownloading, DownloadedChunk, StopDownloading, \
    DownloadingProgress, PlaylistUpdate
from .utils import BaseEvent, Subscriber, retry_on_exception


class ConsoleView(Subscriber):
    def __init__(self) -> None:
        super().__init__()
        self._progress = DownloadingProgress()

    def handle(self, event: BaseEvent) -> None:
        if isinstance(event, CheckStatus):
            print(f'Looking for stream on {event.channel}')
        elif isinstance(event, WaitLiveVideo):
            print('Looking for recording video')
        elif isinstance(event, StartDownloading):
            self._progress = DownloadingProgress()
        elif isinstance(event, PlaylistUpdate):
            self._progress.total_segments = event.total_size
            self._progress.last_chunk_size = event.to_load
            self._progress.downloaded_segments = 0
        elif isinstance(event, DownloadedChunk):
            self._progress.chunk_loaded()
            print(f'\rLast: {self._progress.downloaded_segments:>5}/{self._progress.last_chunk_size:>5}  '
                  f'Total: {self._progress.total_downloaded_segments:>5}/{self._progress.total_segments:>5}', end='')
        elif isinstance(event, StopDownloading):
            print('')
        elif isinstance(event, WaitStream):
            print(f'No live stream. Waiting {event.time/60:.1f} min')


class TelegramView(Subscriber):
    def __init__(self, token: str, chat_id: str) -> None:
        super().__init__()
        self.token = token
        self.chat_id = chat_id

    def handle(self, event: BaseEvent) -> None:
        if isinstance(event, StartDownloading):
            self.send_message(f'Start downloading {event.id}')
        elif isinstance(event, StopDownloading):
            self.send_message('Downloading successfully')

    @retry_on_exception(requests.exceptions.RequestException, max_tries=50)
    def send_message(self, message: str) -> None:
        request = requests.post(f'https://api.telegram.org/bot{self.token}/sendMessage',
                                params={'chat_id': self.chat_id, 'text': message}, timeout=2)
        request.raise_for_status()
