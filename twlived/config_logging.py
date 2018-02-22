import logging.config
from pathlib import Path

from ruamel.yaml import safe_load as yaml_load


def setup_logging(path: str = 'logging.yaml', level: int = logging.INFO) -> None:
    if Path(path).exists():
        with open(path, 'r') as file:
            config_dict = yaml_load(file.read())
        logging.config.dictConfig(config_dict)
    else:
        logging.basicConfig(level=level)


log = logging.getLogger('twlived')
