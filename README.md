# twLiveD

Python 3.6+

Required packages:
[requests](https://github.com/requests/requests/) (http requests),
[pydantic](https://github.com/samuelcolvin/pydantic) (data validation),
[strictyaml](https://github.com/crdoconnor/strictyaml) (.yaml creation, validation),
[m3u8](https://github.com/globocom/m3u8) (parsing HLS),
[iso8601](https://bitbucket.org/micktwomey/pyiso8601) (parsing dates),
[mypy-extensions](https://github.com/python/mypy/tree/master/extensions) (extended type hints).

The script and lib are made for recording broadcasts and VODs from
[Twitch.tv](https://twitch.tv/).

Main purpose of default script is downloading live broadcast without
mute from currently recording VOD.
This allows you to create a good VOD storage with info from Twitch API.
The library **doesn't use** `ffmpeg` or `avconv` for downloading because
corresponding HLS-playlist are always finalized.
Library automatically detects when VOD is completed.
Default script (`launcher.py`) actions:
1. Checkup when the stream on channel goes `live`.
2. Wait until VOD corresponding to the stream appears in Twitch API.
(by difference between stream's `started_at` and VOD's `created_at`)
3. Download VOD while its duration is increasing.
4. Move file to storage.
5. Go to 1.

Library use latest Twitch API Helix ([docs](https://dev.twitch.tv/docs/api/reference)).
All broadcasts will be saved `*.ts` as it presented on twitch.tv.
Use `ffmpeg` after if you want to convert files to another format.

You can enable telegram notifications about start/stop downloading
 and fatal errors if you want.

## Install
Install [pipenv](https://github.com/pypa/pipenv/) if it doen't installed yet.
```
git clone https://github.com/tausackhn/twlived.git
cd twlived && pipenv --python 3.6 && pipenv install && pipenv shell
```

## Usage
Run `launcher.py` to generate configuration file template `config.yaml`.

```
pipenv run launcher.py
```

Open `config.yml` and edit it.
Necessary positions are marked with `<>`.
To get `client-id` you should go https://dev.twitch.tv/dashboard/apps and `Register your application`.
 
After all run again to start proccess
```
pipenv run launcher.py
```

## TODOs
- [ ] Add authorization flow for private VODs.
- [ ] Add support for live broadcasts. (Streamer could turn off recording VODs.)
- [ ] Add support for all type of video.