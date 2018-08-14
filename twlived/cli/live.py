from ._common import Command, COMMON_ARGS, SetStoragePathAction


def _live(args):
    print(args)


command = Command(
    name='live',
    description='Continuously wait and download live streams from a channel on Twitch.TV',
    func=_live,
    arguments=COMMON_ARGS + [
        # Twitch API configuration
        (['--quality', '-q'], {
            'help':    'stream quality, default: chunked (original)',
            'default': 'chunked',
        }),

        # live command configuration
        (['--channel', '-c'], {
            'help':     'Twitch.TV channel name',
            'required': True,
        }),
        (['--source'], {
            'choices': {'vod', 'live'},
            'help':    'stream source, default: vod',
            'default': 'vod',
        }),
        (['--webhook-checker'], {
            'help':    'set up and use Twitch API webhook-based stream checker on given hostname',
            'metavar': 'HOSTNAME',
        }),

        # Storage configuration
        (['--filename-template'], {
            'help':    'template string for filename, default: {id} {date:%Y-%m-%d} {title}.ts',
            'default': '{id} {date:%Y-%m-%d} {title}.ts',
            'metavar': 'TEMPLATE',
        }),
        (['--download-path'], {
            'help':    'path to a directory for downloads, default: . (current directory)',
            'action':  SetStoragePathAction,
            'metavar': 'DIR',
            'default': '.',
        }),

        # Telegram notifications configuration
        (['--telegram-bot-token'], {
            'help':    'a telegram bot token',
            'metavar': 'TG_TOKEN',
        }),
        (['--telegram-notify'], {
            'help':    'telegram channels to be notified',
            'nargs':   '*',
            'metavar': 'TG_CHANNEL',
            'action':  'append',
        }),
    ]
)
