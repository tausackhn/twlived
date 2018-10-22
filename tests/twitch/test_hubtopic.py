import pytest

from twlived.twitch import HubTopic


class TestHubTopic:
    def test_follows(self):
        assert HubTopic.follows(from_id='1336') == 'https://api.twitch.tv/helix/users/follows?first=1&from_id=1336'
        assert HubTopic.follows(to_id='1337') == 'https://api.twitch.tv/helix/users/follows?first=1&to_id=1337'
        assert HubTopic.follows(from_id='1336', to_id='1337') == ('https://api.twitch.tv/helix/'
                                                                  'users/follows?first=1&from_id=1336&to_id=1337')
        with pytest.raises(ValueError):
            HubTopic.follows()

    def test_streams(self):
        assert HubTopic.streams('5678') == 'https://api.twitch.tv/helix/streams?user_id=5678'
