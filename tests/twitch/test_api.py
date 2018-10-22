import aiohttp
import pytest

from twlived.twitch import StreamInfo, TwitchAPI, TwitchAPIError, TwitchAPIHelix, TwitchAPIv5

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope='module')
async def twitch_api(client_id, client_secret):
    async with TwitchAPI(client_id, client_secret=client_secret) as twitch_api:
        yield twitch_api


@pytest.fixture(scope='function')
async def random_channel(twitch_api):
    api_v5: TwitchAPIv5 = twitch_api.get_api('v5')
    streams = await api_v5.get_live_streams(limit=1)
    return streams['streams'][0]['channel']['name']


@pytest.mark.client_id
class TestTwitchAPI:
    async def test_api_default_version(self, twitch_api):
        assert twitch_api.version == 'v5'
        assert isinstance(twitch_api.api, TwitchAPIv5)

    async def test_api_version_change(self, twitch_api):
        for version in TwitchAPI.VERSIONS:
            twitch_api.version = version
            assert isinstance(twitch_api.api, type(twitch_api.get_api(version)))
        with pytest.raises(TwitchAPIError):
            twitch_api.version = 'v3'

    async def test_get_api(self, twitch_api):
        assert isinstance(twitch_api.get_api('Helix'), TwitchAPIHelix)
        assert isinstance(twitch_api.get_api('v5'), TwitchAPIv5)
        with pytest.raises(TwitchAPIError):
            twitch_api.get_api('v3')

    @pytest.mark.parametrize('version', TwitchAPI.VERSIONS)
    async def test_get_stream(self, twitch_api, version, random_channel):
        twitch_api.version = version
        await twitch_api.get_stream(random_channel)

    @pytest.mark.parametrize('version', TwitchAPI.VERSIONS)
    async def test_get_stream_invalid_channel(self, twitch_api, version):
        twitch_api.version = version
        with pytest.raises(TwitchAPIError):
            await twitch_api.get_stream('a')

    @pytest.mark.parametrize('version', TwitchAPI.VERSIONS)
    async def test_get_videos(self, twitch_api, version):
        twitch_api.version = version
        response = await twitch_api.get_videos('guit88man', video_type='highlight', limit=110)
        assert len(response) == 110
        assert all(map(lambda v: v.video_type == 'highlight', response))

    @pytest.mark.parametrize('version', TwitchAPI.VERSIONS)
    async def test_get_video(self, twitch_api, version):
        twitch_api.version = version
        video = await twitch_api.get_video('303908553')
        assert video
        with pytest.raises(aiohttp.ClientResponseError, message='Bad Request'):
            await twitch_api.get_video('abc')

    @pytest.mark.parametrize('version', TwitchAPI.VERSIONS)
    async def test_get_streams(self, twitch_api, version, random_channel):
        twitch_api.version = version
        streams = await twitch_api.get_streams([random_channel, 'lirik', 'elajazz', 'a'])
        assert len(streams) > 0
        assert isinstance(streams[0], StreamInfo)

    async def test_get_variant_playlist(self, twitch_api):
        response = await twitch_api.get_variant_playlist('303908553')
        assert response

    async def test_get_live_variant_playlist(self, twitch_api, random_channel):
        response = await twitch_api.get_live_variant_playlist(random_channel)
        assert response
