import logging
from datetime import timedelta
from typing import Dict, List, NamedTuple, Optional, Union

from configargparse import ArgParser, YAMLConfigFileParser
from iso8601 import parse_date

from . import download, live, shell
from ._common import Command

log = logging.getLogger(__name__)

DEFAULT_CONFIG_FILE = 'twlived.yaml'
PACKAGE_NAME = 'twlived'
PACKAGE_DESCRIPTION = ''
PACKAGE_WEBSITE = 'https://github.com/tausackhn/twlived'
COMMANDS: List[Command] = list(map(lambda module: getattr(module, 'command'), [live, download, shell]))


class Stream(NamedTuple):
    channel_name: str
    live: bool
    exit_when_done: bool
    use_webhook: bool


class VOD(NamedTuple):
    vod_id: List[str]


class Clip(NamedTuple):
    clip_string: List[str]


class TaskConfiguration(NamedTuple):
    client_id: str
    type: Union[Stream, VOD, Clip]
    folder: str = '.'
    storage_folder: Optional[str] = None
    quality: str = 'chunked'
    storage_template_string: str = '{id} {date}.ts'


def is_video_from_stream(video: Dict[str, str], stream: Dict[str, str]) -> bool:
    # Time between creating VOD and starting stream less than 2 minutes
    return bool(parse_date(video['created_at']) - parse_date(stream['started_at']) < timedelta(minutes=2))


# @handle(StreamUp)


def download_stream(event):
    # user_id = event.stream_info['id']
    # video_info = None
    # while not video_info:
    #     videos_info, _ = twitch_api.get_videos(user_id=user_id, type='archive')
    #     # Select the latest video
    #     video_info = next((video for video in videos_info if is_video_from_stream(video, event.stream_info)), None)
    #     if video_info:
    #         video, path = download_manager.download(video_info['id'],
    #                                                 quality=quality,
    #                                                 video_type=video_info['type'])
    #         # `exist_ok=True` Possible if there have been a network problem.
    #         storage.add_broadcast(video, path, exist_ok=True)
    #         delay = new_delay()
    pass


def main(configuration: TaskConfiguration) -> None:
    # if isinstance(configuration.type, Stream):
    #     twitch_api = TwitchAPI(configuration.client_id)
    #     users = twitch_api.get_users(login=[configuration.type.channel_name])
    #     if not users:
    #         # TODO: replace with someone else
    #         raise Exception
    #     stream_checker = create_checker(WebhookChecker if configuration.type.use_webhook else CommonChecker,
    #                                     twitch_api, [user['id'] for user in users])
    #     stream_checker.connect_to()
    # elif isinstance(configuration.type, VOD):
    #     pass
    pass

    # noinspection PyBroadException,PyPep8
    # try:
    #     delay = new_delay()
    #     while True:
    #         main_publisher.publish(CheckStatus(channel=channel))
    #         streams_info, _ = twitch_api.get_streams(user_login=[channel], type='live')
    #         if streams_info:
    #             stream_info = streams_info[0]
    #             main_publisher.publish(WaitLiveVideo())
    #             videos_info, _ = twitch_api.get_videos(user_id=stream_info['user_id'], type='archive')
    #             # Select the latest video
    #             video_info = next((video for video in videos_info if is_video_from_stream(video, stream_info)), None)
    #             if (video_info and
    #                     # Doesn't downloaded yet
    #                     video_info['id'] not in storage.added_broadcast_ids(video_info['type'])):
    #                 video, path = download_manager.download(video_info['id'],
    #                                                         quality=quality,
    #                                                         video_type=video_info['type'])
    #                 # `exist_ok=True` Possible if there have been a network problem.
    #                 storage.add_broadcast(video, path, exist_ok=True)
    #                 delay = new_delay()
    #         waiting_time = next(delay)
    #         main_publisher.publish(WaitStream(time=waiting_time))
    #         sleep(waiting_time)
    # except KeyboardInterrupt:
    #     pass
    # except:  # noqa
    #     main_publisher.publish(ExceptionEvent(message='Fatal error occurred. twLiveD was down.'))
    #     log.exception('Fatal error')


def get_parser():
    parser = ArgParser(prog=PACKAGE_NAME,
                       description=PACKAGE_DESCRIPTION,
                       epilog=PACKAGE_WEBSITE)

    subparsers = parser.add_subparsers()

    def is_config_file(arg):
        return arg[1].get('is_config_file', False)

    def is_required(arg):
        return arg[1].get('required', False)

    for command in COMMANDS:
        subparser = subparsers.add_parser(command.name,
                                          help=command.description,
                                          default_config_files=[DEFAULT_CONFIG_FILE],
                                          config_file_parser_class=YAMLConfigFileParser)
        subparser.set_defaults(func=command.func)
        for args, kwargs in sorted(command.arguments, key=lambda x: not (is_config_file(x) or is_required(x))):
            subparser.add_argument(*args, **kwargs)

    return parser


def cli():
    parser = get_parser()
    args = parser.parse_args()
    args.func(args)
