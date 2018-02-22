from pydantic import BaseModel

from .utils import BaseEvent


class MainPublisherEvent(BaseEvent):
    pass


class CheckStatus(MainPublisherEvent):
    channel: str


class WaitLiveVideo(MainPublisherEvent):
    pass


class WaitStream(MainPublisherEvent):
    time: int


class DownloaderEvent(BaseEvent):
    pass


class StartDownloading(DownloaderEvent):
    id: str


class PlaylistUpdate(DownloaderEvent):
    total_size: int
    to_load: int


class DownloadedChunk(DownloaderEvent):
    pass


class StopDownloading(DownloaderEvent):
    pass


class DownloadingProgress(BaseModel):  # type: ignore
    total_segments: int = 0
    total_downloaded_segments: int = 0
    last_chunk_size: int = 0
    downloaded_segments: int = 0

    def chunk_loaded(self) -> None:
        self.downloaded_segments += 1
        self.total_downloaded_segments += 1


class StorageEvent(BaseEvent):
    pass


class MovingFile(StorageEvent):
    pass
