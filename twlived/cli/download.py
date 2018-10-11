from ._common import COMMON_ARGS, Command, SetStoragePathAction


def _download():
    pass


command = Command(
    name='download',
    description='Download a stream, VoD or clip',
    func=_download,
    arguments=COMMON_ARGS + [
        # Twitch API configuration
        (['--quality', '-q'], {
            'help':    'video quality, default: chunked (original)',
            'default': 'chunked',
        }),

        # Storage configuration
        (['--filename-template'], {
            'help':    'template string for filename',
            'default': '{id} {date:%Y-%m-%d} {title}.ts',
            'metavar': 'TEMPLATE',
        }),
        (['--download-path'], {
            'help':    'path to a directory for downloads, default: . (current directory)',
            'action':  SetStoragePathAction,
            'metavar': 'DIR',
            'default': '.',
        }),
    ],
)
