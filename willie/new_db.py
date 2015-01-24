import sqlite3
from willie.tools import Nick

class WillieDB(object):

    def __init__(self, filename):
        self.filename = filename

    def connect(self):
        """Return a raw database connection object."""
        return sqlite3.connect(self.filename)

    def execute(self, *args, **kwargs):
        """Execute an arbitrary SQL query against the database.

        Returns a cursor object, on which things like `.fetchall()` can be
        called per PEP 249."""
        with self.connect() as conn:
            cur = conn.cursor()
            return cur.execute(*args, **kwargs)

    def create(self):
        """Create the basic database structure."""
        self.execute(
            'CREATE TABLE nicknames '
            '(nick_id INTEGER, slug STRING PRIMARY KEY, canonical string)'
        )
        self.execute(
            'CREATE TABLE nick_values '
            '(nick_id INTEGER REFERENCES nicknames(nick_id) '
            '    ON UPDATE CASCADE ON DELETE CASCADE,'
            'key STRING, value STRING,'
            'PRIMARY KEY (nick_id, key))'
        )
        self.execute('INSERT INTO nicknames VALUES (?, ?, ?)', [0, '', ''])
        self.execute(
            'CREATE TABLE channel_values '
            '(channel STRING, key STRING, value STRING) '
            'PRIMARY KEY (channel, key)'
        )

    # NICK FUNCTIONS

    def _get_nick_id(self, nick, create=True):
        """Return the internal identifier for a given nick.

        This identifier is unique to a user, and shared across all of that
        user's aliases. If create is True, a new ID will be created if one does
        not already exist"""
        slug = nick.lower()
        nick_id = self.execute('SELECT nick_id from nicknames where slug = ?',
                               [slug]).fetchone()
        if nick_id is None:
            if not create:
                raise ValueError('No ID exists for the given nick')
            self.execute(
                'INSERT INTO nicknames (nick_id, slug, canonical) VALUES '
                '((SELECT max(nick_id) + 1 from nicknames), ?, ?)',
                [slug, nick])
            nick_id = self.execute('SELECT nick_id from nicknames where slug = ?',
                                   [slug]).fetchone()
        return nick_id[0]

    def alias_nick(self, nick, alias):
        """Create an alias for a nick.

        Raises ValueError if the alias already exists. If nick does not already
        exist, it will be added along with the alias."""
        nick = Nick(nick)
        alias = Nick(alias)
        nick_id = self._get_nick_id(nick)
        sql = 'INSERT INTO nicknames (nick_id, slug, canonical) VALUES (?, ?, ?)'
        values = [nick_id, alias.lower(), alias]
        try:
            self.execute(sql, values)
        except sqlite3.IntegrityError:  #TODO check that it's a unique violation
            raise ValueError('Alias already exists.')

    def set_nick_value(self, nick, key, value):
        """Sets the value for a given key to be associated with the nick."""
        nick = Nick(nick)
        nick_id = self._get_nick_id(nick)
        self.execute('INSERT OR REPLACE INTO nick_values VALUES (?, ?, ?)',
                     [nick_id, key, value])

    def get_nick_value(self, nick, key):
        """Retrieves the value for a given key associated with a nick."""
        nick = Nick(nick)
        result = self.execute(
            'SELECT value FROM nicknames, nick_values WHERE slug = ? AND key = ?',
            [nick.lower(), key]
        ).fetchone()
        if result is not None:
            result = result[0]
        return result

    def get_all_nick_values(self, nick):
        """Returns a dict of all values associated with a nick."""
        nick = Nick(nick)
        results = self.execute(
            'SELECT key, value from nicknames, nick_values WHERE slug = ?',
            [nick.lower()]).fetchall()
        results = {key: value for key, value in results}
        return results

    def unalias_nick(self, alias):
        """Removes an alias.

        Raises ValueError if there is not at least one other nick in the group.
        To delete an entire group, use `delete_group`.
        """
        alias = Nick(alias)
        nick_id = self._get_nick_id(alias, False)
        count = self.execute('SELECT COUNT(*) FROM nicknames WHERE nick_id = ?',
                             [nick_id]).fetchone()[0]
        if count == 0:
            raise ValueError('Given alias is the only entry in its group.')
        self.execute('DELETE FROM nicknames WHERE slug = ?', [alias.lower()])

    def delete_nick_group(self, nick):
        """Removes a nickname, and all associated aliases and settings.
        """
        nick = Nick(nick)
        nick_id = self._get_nick_id(nick, False)
        self.execute('DELETE FROM nicknames WHERE id = ?', [nick_id])

    def merge_nick_groups(self, first_nick, second_nick):
        """Merges the nick groups for the specified nicks.

        Takes two nicks, which may or may not be registered.  Unregistered
        nicks will be registered. Keys which are set for only one of the given
        nicks will be preserved. Where multiple nicks have values for a given
        key, the value set for the first nick will be used.

        Note that merging of data only applies to the native key-value store.
        If modules define their own tables which rely on the nick table, they
        will need to have their merging done separately."""
        first_id = self._get_nick_id(Nick(first_nick))
        second_id = self._get_nick_id(Nick(second_nick))
        data = self.execute(
            'UPDATE OR IGNORE nick_values SET nick_id = ? WHERE nick_id = ?',
            [first_id, second_id])
        self.execute('DELETE FROM nick_values WHERE nick_id = ?', [second_id])
        self.execute('UPDATE nick_values SET nick_id = ? WHERE nick_id = ?',
                     [first_id, second_id])

    # CHANNEL FUNCTIONS

    def set_channel_value(self, channel, key, value):
        channel = Nick(channel).lower()
        self.execute('INSERT OR REPLACE INTO channel_values VALUES (?, ?, ?)',
                     [channel, key, value])

    def get_channel_value(self, channel, key):
        """Retrieves the value for a given key associated with a channel."""
        channel = Nick(channel).lower()
        result = self.execute(
            'SELECT value FROM channel WHERE channel = ? AND key = ?',
            [channel, key]
        ).fetchone()
        if result is not None:
            result = result[0]
        return result

    # NICK AND CHANNEL FUNCTIONS

    def get_nick_or_channel_value(self, name, key):
        """Gets the value `key` associated to the nick or channel  `name`.
        """
        name = Nick(name)
        if name.is_nick():
            return self.get_nick_value(trigger.nick, key)
        else:
            return self.get_channel_value(trigger.sender, key)

    def get_preferred_value(self, names, key):
        """Gets the value for the first name which has it set.

        `names` is a list of channel and/or user names. Returns None if none of
        the names have the key set."""
        for name in names:
            value = self.get_nick_or_channel_value(self, name, key)
            if value:
                return value
