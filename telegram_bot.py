import requests


class TelegramBot:
    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id

    def send_message(self, message: str) -> None:
        request = requests.post(f'https://api.telegram.org/bot{self.token}/sendMessage',
                                params={'chat_id': self.chat_id, 'text': message})
        request.raise_for_status()
