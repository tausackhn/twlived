import logging
import shelve
import shutil
from itertools import count
from pathlib import Path
from typing import List, ClassVar, Union, Set, Callable

from iso8601 import parse_date

from .downloader import TwitchVideo
from .utils import sanitize_filename

log = logging.getLogger(__name__)


class Storage:
    DB_FILENAME: ClassVar[str] = 'twlived_db'
    _ALLOWED_BROADCAST_TYPES: ClassVar[Set[str]] = {'archive'}

    def __init__(self, storage_path: Union[Path, str],
                 channel_from_id: Callable[[str], str],
                 vod_path_template: str = '{id} {date:%Y-%m-%d}.ts') -> None:
        self.path = Path(storage_path)
        self.broadcast_template = vod_path_template
        self._channel_from_id = channel_from_id
        self._vod_ids: List[str] = []
        self._create_storage_dir()
        self._db: shelve.DbfilenameShelf = shelve.DbfilenameShelf(str(self.path.joinpath(self.DB_FILENAME).resolve()))

    def added_broadcast_ids(self, broadcast_type: str) -> Set[str]:
        if broadcast_type in self._ALLOWED_BROADCAST_TYPES:
            if broadcast_type not in self._db:
                self._db[broadcast_type] = {}
            return set(self._db[broadcast_type])
        raise DBNotAllowedBroadcastType(f'{broadcast_type} are not allowed for database file')

    def add_broadcast(self, broadcast: TwitchVideo, temp_file: Path, exist_ok: bool = False) -> None:
        log.info(f'Adding broadcast {broadcast.id} related to {temp_file.resolve()}')
        if not exist_ok and broadcast.id in self._vod_ids:
            raise BroadcastExistsError(f'{broadcast.id} already added')
        if not temp_file.exists():
            raise MissingFile(f'No such file {temp_file.resolve()} when {broadcast.id} is adding')
        params = {
            'title': sanitize_filename(broadcast.title, replace_to='_'),
            'id': 'v' + broadcast.id,  # naming backward compatibility with TwitchAPI v5
            'type': broadcast.type,
            'channel': self._channel_from_id(broadcast.user_id),
            'date': parse_date(broadcast.created_at),
        }
        new_path = self.path.joinpath(Path(self.broadcast_template.format(**params)))
        new_path.parent.mkdir(parents=True, exist_ok=True)
        for i in count():
            if new_path.exists():
                new_path = new_path.with_suffix(new_path.suffix + f'.{i:02}')
            else:
                break
        log.info(f'Moving file to storage {temp_file.resolve()} to {new_path.resolve()}')
        shutil.move(temp_file, new_path)
        new_path.chmod(0o755)
        log.info(f'File {temp_file.resolve()} moved successful')
        self.update_db(broadcast, new_path)

    def _create_storage_dir(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        if not self.path.is_dir():
            raise NotADirectoryError('Storage path is not a directory')

    def update_db(self, broadcast: TwitchVideo, file: Path) -> None:
        if broadcast.id in self._db[broadcast.type]:
            self._db[broadcast.type][broadcast.id]['files'].append(file.relative_to(self.path))
        else:
            self._db[broadcast.type][broadcast.id] = {
                'info': broadcast,
                'files': [file.relative_to(self.path)],
            }


class BroadcastExistsError(FileExistsError):
    pass


class MissingFile(IOError):
    pass


class DBError(BaseException):
    pass


class DBNotAllowedBroadcastType(DBError):
    pass
