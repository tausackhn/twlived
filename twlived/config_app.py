from typing import Dict, Any, cast

from strictyaml import as_document, Map, Bool, Regex
from strictyaml import load as yaml_load

_WORD = Regex(r'^[\w]+$')
_PATH = Regex(r'[^<>]+')

CONFIG_FILE = 'config.yaml'
__CONFIG_VERSION = 1
__CONFIG_SCHEMA = Map({
    'version': Regex(f'{__CONFIG_VERSION}'),
    'twitch': Map({'client_id': _WORD}),
    'main': Map({'channel': _WORD, 'quality': Regex(r'^[\w]*$'), 'temp_dir': _PATH}),
    'storage': Map({'path': _PATH, 'vod_path': _PATH}),
    'telegram': Map({'enabled': Bool(), 'api_token': Regex(r'^[\w:_\-]+$'), 'chat_id': _WORD}),
})


def load(path: str = CONFIG_FILE) -> Dict[str, Any]:
    with open(path, 'rt') as file:
        return cast(Dict[str, Any], yaml_load(file.read(), schema=__CONFIG_SCHEMA).data)


def create(path: str = CONFIG_FILE) -> None:
    with open(path, 'w') as file:
        config = as_document({
            'version': __CONFIG_VERSION,
            'twitch': {
                'client_id': '<your client-id>',
            },
            'main': {
                'channel': '<twitch channel>',
                'quality': '<quality>',
                'temp_dir': '<path to temporary directory>',
            },
            'storage': {
                'path': '<path where vods should be stored>',
                'vod_path': '<"{{channel}}/{{id}} {{date:%Y-%m-%d}} {{title}}.ts">',
            },
            'telegram': {
                'enabled': False,
                'api_token': '<Telegram bot API token>',
                'chat_id': '<your chat id>',
            },
        })

        comment_quality = 'Depends on stream. Leave blank for source (chunked) quality.'
        comment_vod_path = (
            'Python 3.6 f-string. Valid arguments: {{title}} {{id}} {{type}} {{channel}} {{game}} {{date}}\n'
            '\'*\' will be added to the new filename if file already exist in storage')
        config.as_marked_up()['main'].yaml_set_comment_before_after_key('quality', before=comment_quality, indent=2)
        config.as_marked_up()['storage'].yaml_set_comment_before_after_key('vod_path', before=comment_vod_path,
                                                                           indent=2)
        file.write(config.as_yaml())
