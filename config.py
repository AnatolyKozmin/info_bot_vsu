import os
from dotenv import load_dotenv
load_dotenv()


class Settings():
    TOKEN = os.getenv('TOKEN')
    DB_URL = os.getenv('DOCKER_DB_URL') or os.getenv('DB_URL')
    GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID', '-1000000000000'))
    ADMINS = set(map(int, os.getenv('ADMINS', '').split(','))) if os.getenv('ADMINS') else set()


settings = Settings()