from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple, Union

from configargparse import Action

CArg = Tuple[List[str], Dict[str, Any]]


class Command(NamedTuple):
    name: str
    description: str
    func: Callable
    arguments: List[CArg]


class SetStoragePathAction(Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)

        default_storage_path = getattr(namespace, 'storage_path')
        try:
            default_storage_path = default_storage_path % values
        except TypeError:
            # storage_path already defined
            pass
        setattr(namespace, 'storage_path', default_storage_path)


COMMON_ARGS = [
    (['--config'], {
        'help':           'path to configuration file',
        'metavar':        'FILE',
        'is_config_file': True,
    }),

    # Twitch API configuration
    (['--client-id', '-ci'], {
        'help':     'Twitch.TV API client id',
        'metavar':  'ID',
        'required': True,
    }),

    # Storage configuration
    (['--storage-path'], {
        'help':    'path to a twlived\'s storage directory, default: same as --download-path, . by default',
        'metavar': 'DIR',
        'default': '%s',
    }),
]
