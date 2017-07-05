import requests


class TelegramBot:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id

    def send_message(self, message):
        r = requests.post(f'https://api.telegram.org/bot{self.token}/sendMessage',
                          params={'chat_id': self.chat_id, 'text': message})
        r.raise_for_status()
