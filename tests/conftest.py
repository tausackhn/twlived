def pytest_addoption(parser):
    parser.addoption('--client-id', action='store', default=None, help='Twitch API client id')
    parser.addoption('--client-secret', action='store', default=None, help='Twitch API secret corresponded client id')
