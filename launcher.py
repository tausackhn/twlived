from requests.exceptions import RequestException
from strictyaml import YAMLValidationError

from twlived import (config_app, setup_logging, log, TwitchAPI, Storage, TwitchDownloadManager, ConsoleView,
                     MainPublisherEvent, DownloaderEvent, ExceptionEvent, TelegramView, main)
from twlived.utils import retry_on_exception, Provider, Publisher

if __name__ == '__main__':
    setup_logging()
    log = log.getChild(__name__)
    try:
        config = config_app.load()
    except (FileNotFoundError, YAMLValidationError) as error:
        if isinstance(error, FileNotFoundError):
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
                               request_wrapper=retry_on_exception(RequestException, wait=6, max_tries=10))
        storage = Storage(config['storage']['path'],
                          channel_from_id=lambda id_: str(twitch_api.get_users(id=[id_])[0]['login']),
                          vod_path_template=config['storage']['vod_path'])
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
            telegram.subscribe(ExceptionEvent)

        main(channel, quality, main_publisher, twitch_api, download_manager, storage)
