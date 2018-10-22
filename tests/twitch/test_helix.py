import pytest

from tests.twitch.conftest import bad_calls_ids, bad_calls_list
from twlived.twitch import HelixData, TwitchAPIError, TwitchAPIHelix

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope='module')
async def helix_api(client_id):
    async with TwitchAPIHelix(client_id) as api:
        yield api


@pytest.fixture(scope='module')
async def authorized_helix_api(client_id, client_secret):
    async with TwitchAPIHelix(client_id, client_secret=client_secret) as api:
        yield api


bad_calls = {
    TwitchAPIHelix.get_streams:          [
        ((), {'game_id': ['123'] * (TwitchAPIHelix.MAX_IDS + 1)}),
        ((), {'first': TwitchAPIHelix.MAX_IDS + 1}),
    ],
    TwitchAPIHelix.get_videos:           [
        ((), {}),
        ((), {'id': '123', 'user_id': '123'}),
        ((), {'id': ['123'] * (TwitchAPIHelix.MAX_IDS + 1)}),
        ((), {'user_id': '123', 'after': 'abc', 'before': 'abc'}),
        ((), {'user_id': '123', 'first': TwitchAPIHelix.MAX_IDS + 1}),
        ((), {'user_id': '123', 'period': 'year'}),
        ((), {'user_id': '123', 'sort': 'name'}),
        ((), {'user_id': '123', 'type': 'broadcast'}),
    ],
    TwitchAPIHelix.get_users:            [
        ((), {}),
        ((), {'id': ['123'] * (TwitchAPIHelix.MAX_IDS + 1)}),
        ((), {'login': ['123'] * (TwitchAPIHelix.MAX_IDS + 1)}),
    ],
    TwitchAPIHelix.get_clips:            [
        ((), {}),
        ((), {'broadcaster_id': '123', 'game_id': '123'}),
        ((), {'id': ['Kappa'] * (TwitchAPIHelix.MAX_IDS + 1)}),
        ((), {'broadcaster_id': '123', 'after': 'abc', 'before': 'abc'}),
        ((), {'broadcaster_id': '123', 'first': TwitchAPIHelix.MAX_IDS + 1}),
    ],
    TwitchAPIHelix.get_games:            [
        ((), {}),
        ((), {'id': '123', 'name': 'abc'}),
        ((), {'id': '123' * (TwitchAPIHelix.MAX_IDS + 1)}),
    ],
    TwitchAPIHelix.get_top_games:        [
        ((), {'after': 'abc', 'before': 'abc'}),
        ((), {'first': TwitchAPIHelix.MAX_IDS + 1}),
    ],
    TwitchAPIHelix.get_streams_metadata: [
        ((), {'user_login': ['abc'] * (TwitchAPIHelix.MAX_IDS + 1)}),
        ((), {'first': TwitchAPIHelix.MAX_IDS + 1}),
        ((), {'after': 'abc', 'before': 'abc'}),
    ],
    TwitchAPIHelix.get_users_follows:    [
        ((), {}),
        ((), {'from_id': '123', 'first': TwitchAPIHelix.MAX_IDS + 1}),
    ],
}


@pytest.mark.client_id
class TestTwitchAPIHelix:
    async def test_get_streams(self, helix_api):
        helix_data = await helix_api.get_streams()
        assert isinstance(helix_data, HelixData)
        assert len(helix_data.data) == 20
        assert helix_data.cursor
        keys = {'user_id', 'game_id', 'title', 'type', 'started_at'}
        for key in keys:
            assert all(map(lambda s: s.get(key, None) is not None, helix_data.data))

    async def test_get_streams_user_login(self, helix_api):
        helix_data = await helix_api.get_streams(user_login=['guit88man', 'browjey', 'zik_', 'lirik'])
        assert len(helix_data.data) <= 4

    async def test_get_streams_user_id(self, helix_api):
        helix_data = await helix_api.get_streams(user_id=['7236692', '23161357'])
        assert len(helix_data.data) <= 2

    async def test_get_streams_pagination(self, helix_api):
        helix_data = await helix_api.get_streams()

        helix_data_next = await helix_api.get_streams(after=helix_data.cursor)
        assert helix_data_next.cursor

        helix_data_prev = await helix_api.get_streams(before=helix_data_next.cursor)
        assert len(helix_data_prev.data) == 20

        with pytest.raises(ValueError):
            await helix_api.get_streams(after=helix_data.cursor, before=helix_data.cursor)

    async def test_get_streams_first(self, helix_api):
        helix_data = await helix_api.get_streams(first=10, game_id=['417752', '29307'])
        assert len(helix_data.data) == 10

    async def test_get_videos_id(self, helix_api):
        highlights = ['295118287', '291866779']
        uploads = ['187825618']
        past_broadcasts = ['296424784', '296303251']
        helix_data = await helix_api.get_videos(id=highlights + uploads + past_broadcasts)
        assert isinstance(helix_data, HelixData)
        assert len(helix_data.data) >= len(highlights) + len(uploads)
        keys = {'id', 'user_id', 'title', 'type'}
        for key in keys:
            assert all(map(lambda v: v.get(key, None) is not None, helix_data.data))
        assert all(map(lambda v: v['user_id'] == '25604128', helix_data.data))

    async def test_get_videos_user_id(self, helix_api):
        helix_data = await helix_api.get_videos(user_id='25604128', first=30)
        assert helix_data.cursor
        assert len(helix_data.data) == 30

    async def test_get_videos_game_id(self, helix_api):
        helix_data = await helix_api.get_videos(game_id='417752')
        assert helix_data.cursor
        assert len(helix_data.data) == 20

    async def test_get_videos_type(self, helix_api):
        video_type = 'archive'
        helix_data = await helix_api.get_videos(user_id='25604128', type=video_type)
        assert all(map(lambda v: v['type'] == video_type, helix_data.data))

    async def test_get_users_login(self, helix_api):
        logins = {'guit88man', 'lirik', 'elajjaz'}
        users = await helix_api.get_users(login=list(logins))
        assert len(users) == len(logins)
        assert all(map(lambda u: u['login'] in logins, users))

    async def test_get_users_id(self, helix_api):
        ids = {'44322889', '23161357'}
        users = await helix_api.get_users(id=list(ids))
        assert len(users) == len(ids)
        assert all(map(lambda u: u['id'] in ids, users))

    async def test_get_clips_broadcaster_id(self, helix_api):
        helix_data = await helix_api.get_clips(broadcaster_id='25604128', first=30)
        assert isinstance(helix_data, HelixData)
        assert len(helix_data.data) == 30
        keys = {'created_at', 'creator_id', 'game_id', 'id', 'title', 'video_id', 'url'}
        for key in keys:
            assert all(map(lambda v: v.get(key, None) is not None, helix_data.data))

    async def test_get_clips_id(self, helix_api):
        ids = {
            'SecretiveCarefulSheepM4xHeh',
            'EsteemedNiceNikudonKreygasm',
        }
        helix_data = await helix_api.get_clips(id=list(ids))
        assert isinstance(helix_data, HelixData)
        assert helix_data.cursor is None
        assert all(map(lambda v: v['broadcaster_id'] == '25604128', helix_data.data))

    async def test_get_games_id(self, helix_api):
        games = {
            '493057': "PLAYERUNKNOWN'S BATTLEGROUNDS",
            '490292': 'Dark Souls III',
        }
        data = await helix_api.get_games(id=list(games.keys()))
        assert all(map(lambda g: g['name'] == games[g['id']], data))

    async def test_get_games_name(self, helix_api):
        games = {
            '29433':  'Dark Souls',
            '490292': 'Dark Souls 3',
        }
        data = await helix_api.get_games(name=list(games.values()))
        assert {game['id'] for game in data} == set(games.keys())

    async def test_get_top_games(self, helix_api):
        helix_data = await helix_api.get_top_games()
        assert isinstance(helix_data, HelixData)
        assert helix_data.cursor

    @pytest.mark.skip('Twitch API returns one less result')
    async def test_get_top_games_first(self, helix_api):
        n = 40
        helix_data = await helix_api.get_top_games(first=n)
        assert len(helix_data.data) == n

    async def test_get_top_games_pagination(self, helix_api):
        n = 5
        helix_data = await helix_api.get_top_games(first=n)
        helix_data_next = await helix_api.get_top_games(after=helix_data.cursor, first=n)
        helix_data_prev = await helix_api.get_top_games(before=helix_data_next.cursor, first=n)
        assert len(helix_data.data) == n
        assert len(helix_data_next.data) == n
        assert len(helix_data_prev.data) <= n

    async def test_get_streams_metadata(self, helix_api):
        n = 30
        helix_data = await helix_api.get_streams_metadata(first=n)
        assert isinstance(helix_data, HelixData)
        assert len(helix_data.data) == n
        assert helix_data.cursor
        keys = {'user_id', 'game_id', 'overwatch', 'hearthstone'}
        for key in keys:
            assert all(map(lambda s: key in s, helix_data.data))

    async def test_get_users_follows(self, helix_api):
        n = 25
        user_id = '25604128'
        helix_data = await helix_api.get_users_follows(first=n, from_id=user_id)
        assert isinstance(helix_data, HelixData)
        assert helix_data.cursor
        assert len(helix_data.data) == n

        helix_data = await helix_api.get_users_follows(first=n, to_id=user_id)
        assert helix_data.cursor
        assert len(helix_data.data) == n

    @pytest.mark.client_secret
    async def test_get_webhook_subscriptions(self, helix_api, authorized_helix_api):
        with pytest.raises(TwitchAPIError, message='Requires client_secret'):
            await helix_api.get_webhook_subscriptions()
        helix_data = await authorized_helix_api.get_webhook_subscriptions()
        assert isinstance(helix_data, HelixData)
        assert 0 <= len(helix_data.data) < 20

    @pytest.mark.parametrize('method,parameters', bad_calls_list(bad_calls), ids=bad_calls_ids(bad_calls))
    async def test_bad_calls(self, helix_api, method, parameters):
        with pytest.raises(ValueError):
            args, kwargs = parameters
            await method(helix_api, *args, **kwargs)

    async def test_access_token(self, helix_api, authorized_helix_api):
        with pytest.raises(TwitchAPIError):
            assert await helix_api.access_token
        assert await authorized_helix_api.access_token
