from contextlib import suppress
from time import sleep

import requests
from strictyaml import YAMLValidationError

from twlived import config_app
from twlived.config_logging import setup_logging, log
from twlived.events import MainPublisherEvent, CheckStatus, WaitLiveVideo, WaitStream, DownloaderEvent
from twlived.storage import Storage, TwitchDownloadManager
from twlived.twitch_api import TwitchAPI, NoValidVideo
from twlived.utils import delay_generator, Provider, Publisher, retry_on_exception
from twlived.view import ConsoleView, TelegramView

setup_logging()
log = log.getChild(__name__)

try:
    config = config_app.load()
except (FileNotFoundError, YAMLValidationError) as error:
    if error is FileNotFoundError:
        config_file = config_app.CONFIG_FILE
        config_app.create(path=config_file)
        print(f'Configuration file {config_file} created! Please check it before second run.')
    else:
        print(error)
    exit(1)
else:
    channel = config['main']['channel'].lower()
    quality = config['main']['quality'] or 'chunked'
    twitch_api = TwitchAPI(config['twitch']['client_id'],
                           request_wrapper=retry_on_exception(requests.exceptions.RequestException,
                                                              wait=0.5, max_tries=10))
    storage = Storage(storage_path=config['storage']['path'], vod_path_template=config['storage']['vod_path'])
    message_center = Provider()
    download_manager = TwitchDownloadManager(twitch_api, config['main']['temp_dir'])
    main_publisher = Publisher()
    console = ConsoleView()
    message_center.connect(main_publisher, download_manager, console)
    console.subscribe(MainPublisherEvent)
    console.subscribe(DownloaderEvent)
    if config['telegram']['enabled']:
        telegram = TelegramView(token=config['telegram']['api_token'], chat_id=config['telegram']['chat_id'])
        telegram.connect_to(message_center)
        telegram.subscribe(DownloaderEvent)


@retry_on_exception(requests.exceptions.RequestException)
def main() -> None:
    delay = delay_generator(900, 60)
    while True:
        main_publisher.publish(CheckStatus(channel=channel))
        if twitch_api.get_stream_status(channel) == 'online':
            main_publisher.publish(WaitLiveVideo())
            # VOD obtain status `recording` before stream API changed status to `offline`
            with suppress(NoValidVideo):
                for video_info in twitch_api.get_recording_videos(channel):
                    if video_info['_id'] not in storage.added_broadcast_ids(video_info['broadcast_type']):
                        video, path = download_manager.download(video_info['_id'], quality=quality)
                        storage.add_broadcast(video, path, exist_ok=True)
                        delay = delay_generator(900, 60)
        waiting_time = next(delay)
        main_publisher.publish(WaitStream(time=waiting_time))
        sleep(waiting_time)


if __name__ == '__main__':
    # noinspection PyBroadException,PyPep8
    try:
        main()
    except KeyboardInterrupt:
        pass
    except:  # noqa
        log.exception('Fatal error')
