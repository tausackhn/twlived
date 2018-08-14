from typing import Collection, List, Optional
from urllib.parse import urljoin

from .base import BaseAPI, JSONT, ResponseT, URLParameterT, bool_to_str, filter_none_and_empty


class TwitchAPIv5(BaseAPI):
    """Class implementing part of Twitch API v5."""

    DOMAIN: str = 'https://api.twitch.tv/kraken/'
    MAX_LIMIT: int = 100
    DIRECTIONS = {'asc', 'desc'}
    BROADCAST_TYPES = {'archive', 'highlight', 'upload'}
    VIDEOS_SORT = {'time', 'views'}
    PERIODS = {'day', 'week', 'month', 'all'}
    STREAM_TYPES = {'live', 'playlist', 'all', 'premiere', 'rerun'}
    SORT_BY = {'created_at', 'last_broadcast', 'login'}

    def __init__(self, client_id: str, *, retry: bool = False) -> None:
        super().__init__(retry=retry)
        self._session.headers.update({
            'Client-ID': client_id,
            'Accept':    'application/vnd.twitchtv.v5+json'
        })

    def get_cheermotes(self, *, channel_id: str = None) -> JSONT:
        return self._kraken_get('bits/actions', params={'channel_id': channel_id})

    def get_channel_by_id(self, channel_id: str) -> JSONT:
        return self._kraken_get(f'channels/{channel_id}')

    def get_channel_followers(self, channel_id: str, *,
                              limit: int = 25,
                              offset: int = 0,
                              cursor: Optional[str] = None,
                              direction: Optional[str] = 'desc') -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')
        if direction not in TwitchAPIv5.DIRECTIONS:
            raise ValueError(f'Invalid direction. Valid values: {TwitchAPIv5.DIRECTIONS}')

        params = {
            'limit':     str(limit),
            'offset':    str(offset),
            'cursor':    cursor,
            'direction': direction
        }

        return self._kraken_get(f'channels/{channel_id}/follows', params=params)

    def get_channel_teams(self, channel_id: str) -> JSONT:
        return self._kraken_get(f'channels/{channel_id}/teams')

    def get_channel_videos(self, channel_id: str, *,
                           limit: int = 10,
                           offset: int = 0,
                           broadcast_type: Optional[Collection[str]] = None,
                           language: Optional[str] = None,
                           sort: str = 'time') -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')
        if broadcast_type and set(broadcast_type) - TwitchAPIv5.BROADCAST_TYPES:
            raise ValueError(f'Invalid direction. Valid values: {TwitchAPIv5.BROADCAST_TYPES}')
        if sort not in TwitchAPIv5.VIDEOS_SORT:
            raise ValueError(f'Invalid parameter sort. Valid values: {TwitchAPIv5.VIDEOS_SORT}')

        params = {
            'limit':          str(limit),
            'offset':         str(offset),
            'broadcast_type': broadcast_type,
            'language':       language,
            'sort':           sort
        }

        return self._kraken_get(f'channels/{channel_id}/videos', params=params)

    def get_channel_communities(self, channel_id: str) -> JSONT:
        return self._kraken_get(f'channels/{channel_id}/communities')

    def get_chat_badges(self, channel_id: str) -> JSONT:
        return self._kraken_get(f'chat/{channel_id}/badges')

    def get_chat_emoticons(self, *, emotesets: Optional[List[int]] = None) -> JSONT:
        emotesets = emotesets or []
        params = {'emotesets': list(map(str, emotesets))}

        return self._kraken_get('chat/emoticon_images', params=params)

    def get_all_chat_emoticons(self) -> JSONT:
        return self._kraken_get('chat/emoticons')

    def get_clip(self, slug: str) -> JSONT:
        return self._kraken_get(f'clips/{slug}')

    def get_top_clips(self, *,
                      channel: Optional[str] = None,
                      cursor: Optional[str] = None,
                      game: Optional[str] = None,
                      language: str = '',
                      limit: int = 10,
                      period: str = 'week',
                      trending: bool = False) -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')
        if period not in TwitchAPIv5.PERIODS:
            raise ValueError(f'Invalid period. Valid values: {TwitchAPIv5.PERIODS}')

        params = {
            'channel':  channel,
            'cursor':   cursor,
            'game':     game,
            'language': language,
            'limit':    str(limit),
            'period':   period,
            'trending': bool_to_str(trending)
        }

        return self._kraken_get('clips/top', params=params)

    def get_collection_metadata(self, collection_id: str) -> JSONT:
        return self._kraken_get(f'collections/{collection_id}')

    def get_collection(self, collection_id: str, *, include_all_items: bool = False) -> JSONT:
        params = {'include_all_items': bool_to_str(include_all_items)}

        return self._kraken_get(f'collections/{collection_id}/items', params=params)

    def get_collections(self, channel_id: str, *,
                        limit: int = 10,
                        cursor: Optional[str] = None,
                        containing_item: Optional[str] = None) -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')
        if containing_item and not containing_item.startswith('video:'):
            raise ValueError(f'Invalid containing item string. Possible template: \'video:<video id>\'')

        params = {
            'limit':           str(limit),
            'cursor':          cursor,
            'containing_item': containing_item
        }

        return self._kraken_get(f'channels/{channel_id}/collections', params=params)

    def get_community_by_name(self, community_name: str) -> JSONT:
        params = {'name': community_name}
        return self._kraken_get('communities', params=params)

    def get_community_by_id(self, community_id: str) -> JSONT:
        return self._kraken_get(f'communities/{community_id}')

    def get_top_communities(self, *,
                            limit: int = 10,
                            cursor: Optional[str] = None) -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')

        params = {
            'limit':  str(limit),
            'cursor': cursor
        }

        return self._kraken_get('communities/top', params=params)

    def get_top_games(self, *,
                      limit: int = 10,
                      offset: int = 0) -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')

        params = {
            'limit':  str(limit),
            'offset': str(offset)
        }

        return self._kraken_get('games/top', params=params)

    def get_ingest_server_list(self) -> JSONT:
        return self._kraken_get('ingests')

    def search_channels(self, query: str, *,
                        limit: int = 25,
                        offset: int = 0) -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')

        params = {
            'query':  query,
            'limit':  str(limit),
            'offset': str(offset)
        }

        return self._kraken_get('search/channels', params=params)

    def search_games(self, query: str, *, live: bool = False) -> JSONT:
        params = {
            'query': query,
            'live':  bool_to_str(live)
        }

        return self._kraken_get('search/games', params=params)

    def search_streams(self, query: str, *,
                       limit: int = 25,
                       offset: int = 0,
                       hls: Optional[bool] = None) -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')

        params = {
            'query':  query,
            'limit':  str(limit),
            'offset': str(offset),
            'hls':    bool_to_str(hls) if hls is not None else hls
        }

        return self._kraken_get('search/streams', params=params)

    def get_stream(self, user_id: str, *, stream_type: str = 'live') -> JSONT:
        if stream_type not in TwitchAPIv5.STREAM_TYPES:
            raise ValueError(f'Invalid stream type. Valid values: {TwitchAPIv5.STREAM_TYPES}')

        params = {'stream_type': stream_type}

        return self._kraken_get(f'streams/{user_id}', params=params)

    def get_live_streams(self, *,
                         channel: Optional[List[str]] = None,
                         game: Optional[str] = None,
                         language: Optional[str] = None,
                         stream_type: Optional[str] = 'live',
                         limit: int = 25,
                         offset: int = 0) -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')
        if stream_type not in TwitchAPIv5.STREAM_TYPES:
            raise ValueError(f'Invalid stream type. Valid values: {TwitchAPIv5.STREAM_TYPES}')

        params = {
            'channel':     channel,
            'game':        game,
            'language':    language,
            'stream_type': stream_type,
            'limit':       str(limit),
            'offset':      str(offset)
        }

        return self._kraken_get('streams', params=params)

    def get_streams_summary(self, *, game: Optional[str] = None) -> JSONT:
        params = {'game': game}

        return self._kraken_get('streams/summary', params=params)

    def get_featured_streams(self, *, limit: int = 25, offset: int = 0) -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')

        params = {
            'limit':  str(limit),
            'offset': str(offset)
        }

        return self._kraken_get('streams/featured', params=params)

    def get_all_teams(self, *, limit: int = 25, offset: int = 0) -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')

        params = {
            'limit':  str(limit),
            'offset': str(offset)
        }

        return self._kraken_get('teams', params=params)

    def get_team(self, team_name: str) -> JSONT:
        return self._kraken_get(f'teams/{team_name}')

    def get_user_by_id(self, user_id: str, *, update_storage: bool = False) -> JSONT:
        if update_storage or user_id not in self._id_storage:
            self._id_storage[user_id] = self._kraken_get(f'users/{user_id}')

        return self._id_storage[user_id]

    def get_users(self, login: List[str], *, update_storage: bool = False) -> List[JSONT]:
        if len(login) > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify up to {TwitchAPIv5.MAX_LIMIT} logins')
        if update_storage:
            missing_logins = login
        else:
            missing_logins = list(filter(lambda x: x not in self._login_storage, login))

        params = filter_none_and_empty({
            'login': missing_logins
        })

        if params:
            response = self._kraken_get('users', params=params)
            for user in response['users']:
                self._id_storage[user['_id']] = user
                self._login_storage[user['name']] = user

        return list(user for user in (self._login_storage.get(login_, None) for login_ in set(login))
                    if user is not None)

    def get_user_follows(self, user_id: str, *,
                         limit: int = 25,
                         offset: int = 0,
                         direction: str = 'desc',
                         sortby: str = 'created_at') -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')
        if direction not in TwitchAPIv5.DIRECTIONS:
            raise ValueError(f'Invalid direction. Valid values: {TwitchAPIv5.DIRECTIONS}')
        if sortby not in TwitchAPIv5.SORT_BY:
            raise ValueError(f'Invalid parameter sortby. Valid values: {TwitchAPIv5.SORT_BY}')

        params = {
            'limit':     str(limit),
            'offset':    str(offset),
            'direction': direction,
            'sortby':    sortby
        }

        return self._kraken_get(f'user/{user_id}/follows/channels', params=params)

    def get_user_follows_by_channel(self, user_id: str, channel_id: str) -> JSONT:
        return self._kraken_get(f'users/{user_id}/follows/channels/{channel_id}')

    def get_video(self, video_id: str) -> JSONT:
        return self._kraken_get(f'videos/{video_id}')

    def get_top_videos(self, *,
                       limit: int = 10,
                       offset: int = 0,
                       game: Optional[str] = None,
                       period: Optional[str] = 'week',
                       broadcast_type: Optional[Collection[str]] = None,
                       language: str = '',
                       sort: str = 'time') -> JSONT:
        if limit > TwitchAPIv5.MAX_LIMIT:
            raise ValueError(f'You can specify limit up to {TwitchAPIv5.MAX_LIMIT}')
        if period not in TwitchAPIv5.PERIODS:
            raise ValueError(f'Invalid period. Valid values: {TwitchAPIv5.PERIODS}')
        if broadcast_type and set(broadcast_type) - TwitchAPIv5.BROADCAST_TYPES:
            raise ValueError(f'Invalid direction. Valid values: {TwitchAPIv5.BROADCAST_TYPES}')
        if sort not in TwitchAPIv5.VIDEOS_SORT:
            raise ValueError(f'Invalid parameter sort. Valid values: {TwitchAPIv5.VIDEOS_SORT}')

        params = {
            'limit':          str(limit),
            'offset':         str(offset),
            'game':           game,
            'period':         period,
            'broadcast_type': broadcast_type,
            'language':       language,
            'sort':           sort
        }

        return self._kraken_get('videos/top', params=params)

    def _request(self, method: str, url: str, *, params: Optional[URLParameterT] = None) -> ResponseT:
        return super()._request(method, url, params=params)

    def _kraken_get(self, path: str, *, params: Optional[URLParameterT] = None) -> JSONT:
        return self._request('get', urljoin(TwitchAPIv5.DOMAIN, path), params=params).json()
