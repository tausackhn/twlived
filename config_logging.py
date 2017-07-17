# coding=utf-8
import logging.config

import yaml


def setup_logging() -> None:
    with open("log_config.yaml", 'r') as file:
        config_dict = yaml.load(file)

    logging.config.dictConfig(config_dict)


log = logging.getLogger('log')
