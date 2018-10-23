from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple, Optional

from ..utils import BaseEvent


class DownloadingError(Exception):
    pass


class ProgressData(NamedTuple):
    first_segment: Optional[int] = None
    last_segment: Optional[int] = None
    data_size: Optional[float] = None
    complete_segment: Optional[int] = None
    write_segment: Optional[int] = None


@dataclass
class BeginDownloading(BaseEvent):
    video_id: str
    channel_name: str


@dataclass
class BeginDownloadingLive(BaseEvent):
    channel_name: str


@dataclass
class EndDownloading(BaseEvent):
    video_id: str
    channel_name: str


@dataclass
class EndDownloadingLive(BaseEvent):
    channel_name: str


@dataclass
class AwaitingStream(BaseEvent):
    channel_name: str
    sleep_time: float


class StreamType(Enum):
    LIVE = 1
    VOD = 2
