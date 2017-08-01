import logging.config

from ruamel.yaml import safe_load as yaml_load


def setup_logging() -> None:
    with open('log_config.yaml', 'r') as file:
        config_dict = yaml_load(file.read())
    logging.config.dictConfig(config_dict)


LOG = logging.getLogger('log')
