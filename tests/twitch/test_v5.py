import pytest

from tests.twitch.conftest import bad_calls_ids, bad_calls_list
from twlived.twitch import TwitchAPIv5

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope='module')
async def api_v5(client_id):
    async with TwitchAPIv5(client_id) as api:
        yield api


bad_calls = {
    TwitchAPIv5.get_channel_followers: [
        (('123',), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
        (('123',), {'direction': 'left'}),
    ],
    TwitchAPIv5.get_channel_videos:    [
        (('123',), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
        (('123',), {'broadcast_type': 'broadcast'}),
        (('123',), {'sort': 'name'}),
    ],
    TwitchAPIv5.get_top_clips:         [
        ((), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
        ((), {'period': 'year'}),
    ],
    TwitchAPIv5.get_collections:       [
        (('123',), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
        (('123',), {'containing_item': 'file:test'}),
    ],
    TwitchAPIv5.get_top_communities:   [
        ((), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
    ],
    TwitchAPIv5.get_top_games:         [
        ((), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
    ],
    TwitchAPIv5.search_channels:       [
        (('starcraft',), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
    ],
    TwitchAPIv5.search_streams:        [
        (('starcraft',), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
    ],
    TwitchAPIv5.get_stream:            [
        (('123',), {'stream_type': ''}),
    ],
    TwitchAPIv5.get_live_streams:      [
        ((), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
        ((), {'stream_type': ''}),
    ],
    TwitchAPIv5.get_featured_streams:  [
        ((), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
    ],
    TwitchAPIv5.get_all_teams:         [
        ((), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
    ],
    TwitchAPIv5.get_users:             [
        ((['abc'] * (TwitchAPIv5.MAX_LIMIT + 1),), {}),
    ],
    TwitchAPIv5.get_user_follows:      [
        (('123',), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
        (('123',), {'direction': 'up'}),
        (('123',), {'sortby': 'name'}),
    ],
    TwitchAPIv5.get_top_videos:        [
        ((), {'limit': TwitchAPIv5.MAX_LIMIT + 1}),
        ((), {'offset': TwitchAPIv5.MAX_OFFSET + 1}),
        ((), {'period': 'year'}),
        ((), {'broadcast_type': 'broadcast'}),
        ((), {'sort': 'name'}),
    ],
}


@pytest.mark.client_id
class TestTwitchAPIv5:
    async def test_get_cheermotes(self, api_v5):
        response = await api_v5.get_cheermotes(channel_id='23161357')
        assert isinstance(response['actions'], list)
        assert {'backgrounds', 'prefix', 'scales', 'states', 'tiers'}.issubset(response['actions'][0].keys())

    async def test_get_channel_by_id(self, api_v5):
        response = await api_v5.get_channel_by_id('23161357')
        assert {'_id', 'name', 'created_at', 'updated_at', 'status'}.issubset(response.keys())
        assert response['name'] == 'lirik'
        assert response['_id'] == '23161357'

    async def test_get_channel_followers(self, api_v5):
        response = await api_v5.get_channel_followers('23161357')
        assert len(response['follows']) == 25
        assert response['_cursor']

    async def test_get_channel_teams(self, api_v5):
        response = await api_v5.get_channel_teams('23161357')
        assert 'teams' in response.keys()

    async def test_get_channel_videos(self, api_v5):
        response = await api_v5.get_channel_videos('25604128', limit=100)
        assert len(response['videos']) == 100
        assert {'_id', 'created_at', 'broadcast_type', 'game', 'status', 'title'}.issubset(response['videos'][0].keys())
        response = await api_v5.get_channel_videos('25604128', limit=100, broadcast_type=['archive'])
        assert all(map(lambda v: v['broadcast_type'] == 'archive', response['videos']))

    async def test_get_channel_communities(self, api_v5):
        response = await api_v5.get_channel_communities('23161357')
        assert 'communities' in response.keys()

    async def test_get_chat_badges(self, api_v5):
        response = await api_v5.get_chat_badges('23161357')
        assert {'admin', 'broadcaster', 'global_mod', 'mod', 'staff', 'subscriber', 'turbo'}.issubset(response.keys())

    async def test_get_chat_emoticons(self, api_v5):
        response = await api_v5.get_chat_emoticons(emotesets=[46, 19151])
        assert response['emoticon_sets'][str(19151)][0]['code'] == 'TwitchLit'

    async def test_get_clip(self, api_v5):
        response = await api_v5.get_clip('AmazonianEncouragingLyrebirdAllenHuhu')
        assert {'vod', 'game', 'title', 'broadcaster', 'curator', 'created_at'}.issubset(response.keys())

    async def test_get_top_clips(self, api_v5):
        response = await api_v5.get_top_clips()
        assert response['clips']
        assert response['_cursor']
        response = await api_v5.get_top_clips(channel='guit88man', limit=100, period='all')
        assert len(response['clips']) == 100

    async def test_get_collection_metadata(self, api_v5):
        response = await api_v5.get_collection_metadata('HO30ajZC2BS1jw')
        assert {'created_at', 'owner', 'title', 'updated_at'}.issubset(response.keys())

    async def test_get_collection(self, api_v5):
        response = await api_v5.get_collection('HO30ajZC2BS1jw', include_all_items=True)
        assert len(response['items']) == 2

    async def test_get_collections(self, api_v5):
        response = await api_v5.get_collections('25604128', limit=5)
        assert len(response['collections']) == 5

    async def test_get_community_by_name(self, api_v5):
        response = await api_v5.get_community_by_name('programming')
        assert response

    async def test_get_community_by_id(self, api_v5):
        response = await api_v5.get_community_by_id('9d175334-ccdd-4da8-a3aa-d9631f95610e')
        assert response

    async def test_get_top_communities(self, api_v5):
        response = await api_v5.get_top_communities(limit=50)
        assert len(response['communities']) == 50
        assert response['_cursor']

    async def test_get_top_games(self, api_v5):
        response = await api_v5.get_top_games()
        assert response

    @pytest.mark.skip('Twitch API returns one less result')
    async def test_get_top_games_limit(self, api_v5):
        response = await api_v5.get_top_games(limit=30)
        assert len(response['top']) == 30

    async def test_get_ingest_server_list(self, api_v5):
        response = await api_v5.get_ingest_server_list()
        assert response

    async def test_search_channels(self, api_v5):
        response = await api_v5.search_channels('league of legends')
        assert len(response['channels']) == 25

    async def test_search_games(self, api_v5):
        response = await api_v5.search_games('diablo 3')
        assert response['games']

    async def test_search_streams(self, api_v5):
        response = await api_v5.search_streams('league of legends', limit=1)
        assert len(response['streams']) == 1

    async def test_get_stream(self, api_v5):
        response = await api_v5.get_stream('25604128')
        assert response

    async def test_get_live_streams(self, api_v5):
        response = await api_v5.get_live_streams(limit=10)
        assert len(response['streams']) == 10
        keys = {'_id', 'game', 'stream_type', 'channel', 'created_at', 'is_playlist'}
        assert keys.issubset(response['streams'][0].keys())
        response = await api_v5.get_live_streams(channel=['25604128', '23161357'])
        assert response

    async def test_get_streams_summary(self, api_v5):
        response = await api_v5.get_streams_summary()
        assert response

    async def test_get_featured_streams(self, api_v5):
        response = await api_v5.get_featured_streams(limit=1)
        assert response

    async def test_get_all_teams(self, api_v5):
        response = await api_v5.get_all_teams(limit=15)
        assert len(response['teams']) == 15

    async def test_get_team(self, api_v5):
        response = await api_v5.get_team('staff')
        assert response

    async def test_get_user_by_id(self, api_v5):
        response = await api_v5.get_user_by_id('25604128')
        assert response['name'] == 'guit88man'

    async def test_get_users(self, api_v5):
        response = await api_v5.get_users(login=['guit88man', 'lirik'])
        assert response
        assert 'guit88man' in {user['name'] for user in response}

    async def test_get_user_follows(self, api_v5):
        response = await api_v5.get_user_follows('25604128', limit=5)
        assert len(response['follows']) == 5

    async def test_get_user_follows_by_channel(self, api_v5):
        response = await api_v5.get_user_follows_by_channel(user_id='25604128', channel_id='34711476')
        assert response

    async def test_get_video(self, api_v5):
        response = await api_v5.get_video('304574922')
        keys = {'_id', 'broadcast_type', 'channel', 'created_at', 'game', 'status', 'title',
                'viewable'}
        assert keys.issubset(response.keys())

    @pytest.mark.skip('Twitch API always return 500 internal server error')
    async def test_get_top_videos(self, api_v5):
        response = await api_v5.get_top_videos(limit=20, broadcast_type=['highlight'])
        assert response['vods']
        assert all(map(lambda v: v['broadcast_type'] == 'highlight', response['vods']))

    @pytest.mark.parametrize('method,parameters', bad_calls_list(bad_calls), ids=bad_calls_ids(bad_calls))
    async def test_bad_calls(self, api_v5, method, parameters):
        with pytest.raises(ValueError):
            args, kwargs = parameters
            await method(api_v5, *args, **kwargs)
