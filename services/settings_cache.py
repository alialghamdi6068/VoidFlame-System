import time
from database import get_guild_data

class SettingsCache:
    def __init__(self, ttl=15):
        self.ttl = ttl
        self._data = {}

    def get(self, guild_id):
        now = time.monotonic()
        item = self._data.get(int(guild_id))
        if item and now - item[0] < self.ttl:
            return dict(item[1])
        data = get_guild_data(int(guild_id))
        self._data[int(guild_id)] = (now, dict(data))
        return dict(data)

    def invalidate(self, guild_id):
        self._data.pop(int(guild_id), None)

    def clear(self):
        self._data.clear()

settings_cache = SettingsCache()
