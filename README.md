# twLiveD

Python 3.6+

This script waits for live (recording) broadcasts on [Twitch.TV](https://twitch.tv/) and records it then.

The script **doesn't** use `ffmpeg` because twitch.tv live broadcasting system is unstable.
`ffmpeg` hangs sometimes and it can't be caught properly to restart downloading. 
Basic idea is to download already recording broadcast which'll be muted after stream ending in 15 min.
Downloaded broadcasts match perfectly to vods `twitch.tv/videos/v******`.
Another bonus is ignoring short broadcasts (less than ~3 min) which occur sometimes.

All broadcasts will be saved `*.ts` as it presented on twitch.tv. 
Use `ffmpeg` after if you want to convert files to another format.

# Install
```
git clone https://github.com/tausackhn/twlived.git
pip install -r requirements.txt
```

# Use

Run script first time to generate sample configuration file `config.yaml`.

```
python main.py
```

Than open `config.yml` and edit it.
Necessary positions're marked with `<***>`.
To get `client-id` you should go https://www.twitch.tv/settings/connections scroll down and `Register your application`.
 
After simply run again
```
python main.py
```
