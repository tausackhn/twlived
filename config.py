# encoding=utf-8
from pathlib import Path
from typing import Dict

import yaml

basic_config_str = '''\
twitch:
    client_id: <your client-id>

main:
    channel: <twitch channel>
    # Could be one of (source, high, medium, low, mobile, audio only)
    quality: <quality>
    temp_dir: <path to temporary directory>

storage:
    path: <path where vods should be stored>
    # Python 3.6 f-string. Valid arguments: {title} {id} {type} {channel} {game} {date}
    # '*' will be added to the new filename if file already exist in storage
    vod_path: <"{channel}/{id} {date:%Y-%m-%d} {title}.ts">

telegram:
    enabled: False
    api_token: <Telegram bot API token>
    chat_id: <your chat id>
'''


def init(path: str = 'config.yaml') -> Dict:
    if not Path(path).exists():
        create(path)
        print(f'Please check configuration file {path}')
        quit(0)
    return load(path)


def create(path: str) -> None:
    with open(path, 'w') as f:
        f.write(basic_config_str)


def load(path: str) -> Dict:
    with open(path, 'rt') as f:
        config = yaml.safe_load(f.read())  # type: ignore
        validate(config)
        return config


def validate(config: dict) -> None:
    groups = {'twitch', 'main', 'storage'}
    twitch_keys = {'client_id'}
    main_keys = {'channel', 'quality', 'temp_dir'}
    storage_keys = {'path', 'vod_path'}
    error_msg = "'{key}' is empty or some keys missing {keys}"
    if not groups.issubset(config.keys()):
        raise ValidationConfigError(f'Some keys missing {groups - config.keys()}')
    if not config['twitch'] or not twitch_keys.issubset(config['twitch'].keys()):
        raise ValidationConfigError(error_msg.format(key='twitch', keys=twitch_keys - config['twitch'].keys()))
    if not config['main'] or not main_keys.issubset(config['main'].keys()):
        raise ValidationConfigError(error_msg.format(key='main', keys=main_keys - config['main'].keys()))
    if not config['storage'] or not storage_keys.issubset(config['storage'].keys()):
        raise ValidationConfigError(error_msg.format(key='storage', keys=main_keys - config['storage'].keys()))


class ValidationConfigError(Exception):
    pass
