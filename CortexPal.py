import discord
import random
import os
import traceback
import re
import logging
import logging.handlers
import configparser
import datetime
import uuid
import sqlite3
import copy
from discord.ext import commands
from datetime import datetime, timedelta, timezone

PREFIX = '$'

PURGE_DAYS = 180

DICE_EXPRESSION = re.compile('(\d*(d|D))?(4|6|8|10|12)')
DIE_SIZES = [4, 6, 8, 10, 12]

UNTYPED_STRESS = 'General'

ADD_SYNONYMS = ['add', 'give', 'new', 'create']
REMOVE_SYNOYMS = ['remove', 'spend', 'delete', 'subtract']
UP_SYNONYMS = ['stepup', 'up']
DOWN_SYNONYMS = ['stepdown', 'down']
CLEAR_SYNONYMS = ['clear', 'erase']

DIE_FACE_ERROR = '{0} is not a valid die size. You may only use dice with sizes of 4, 6, 8, 10, or 12.'
DIE_STRING_ERROR = '{0} is not a valid die or dice.'
DIE_EXCESS_ERROR = 'You can\'t use that many dice.'
DIE_MISSING_ERROR = 'There were no valid dice in that command.'
DIE_LACK_ERROR = 'That pool only has {0}D{1}.'
DIE_NONE_ERROR = 'That pool doesn\'t have any D{0}s.'
NOT_EXIST_ERROR = 'There\'s no such {0} yet.'
HAS_NONE_ERROR = '{0} doesn\'t have any {1}.'
HAS_ONLY_ERROR = '{0} only has {1} {2}.'
INSTRUCTION_ERROR = '`{0}` is not a valid instruction for the `{1}` command.'
UNKNOWN_COMMAND_ERROR = 'That\'s not a valid command.'
UNEXPECTED_ERROR = 'Oops. A software error interrupted this command.'

PREFIX_OPTION = 'prefix'
BEST_OPTION = 'best'

ABOUT_TEXT = 'CortexPal v1.2.1: a Discord bot for Cortex Prime RPG players.'

# Read configuration.

config = configparser.ConfigParser()
config.read('cortexpal.ini')

# Set up logging.

logHandler = logging.handlers.TimedRotatingFileHandler(filename=config['logging']['file'], when='D', backupCount=9)
logging.basicConfig(handlers=[logHandler], format='%(asctime)s %(message)s', level=logging.DEBUG)

# Set up database.

db = sqlite3.connect(config['database']['file'])
db.row_factory = sqlite3.Row
cursor = db.cursor()

cursor.execute(
'CREATE TABLE IF NOT EXISTS GAME'
'(GUID VARCHAR(32) PRIMARY KEY,'
'SERVER INT NOT NULL,'
'CHANNEL INT NOT NULL,'
'ACTIVITY DATETIME NOT NULL)'
)

cursor.execute(
'CREATE TABLE IF NOT EXISTS GAME_OPTIONS'
'(GUID VARCHAR(32) PRIMARY KEY,'
'KEY VARCHAR(16) NOT NULL,'
'VALUE VARCHAR(256),'
'PARENT_GUID VARCHAR(32) NOT NULL)'
)

cursor.execute(
'CREATE TABLE IF NOT EXISTS DIE'
'(GUID VARCHAR(32) PRIMARY KEY,'
'NAME VARCHAR(64),'
'SIZE INT NOT NULL,'
'QTY INT NOT NULL,'
'PARENT_GUID VARCHAR(32) NOT NULL)'
)

cursor.execute(
'CREATE TABLE IF NOT EXISTS DICE_COLLECTION'
'(GUID VARCHAR(32) PRIMARY KEY,'
'CATEGORY VARCHAR(64) NOT NULL,'
'GRP VARCHAR(64),'
'PARENT_GUID VARCHAR(32) NOT NULL)'
)

cursor.execute(
'CREATE TABLE IF NOT EXISTS RESOURCE'
'(GUID VARCHAR(32) PRIMARY KEY,'
'CATEGORY VARCHAR(64) NOT NULL,'
'NAME VARCHAR(64) NOT NULL,'
'QTY INT NOT NULL,'
'PARENT_GUID VARCHAR(64) NOT NULL)'
)

# Classes and functions follow.

class CortexError(Exception):
    """Exception class for command and rules errors specific to this bot."""

    def __init__(self, message, *args):
        self.message = message
        self.args = args

    def __str__(self):
        return self.message.format(*(self.args))

def get_prefix(bot, message):
    game_info = CortexGame(None, message.guild.id, message.channel.id)
    prefix = game_info.get_option(PREFIX_OPTION)
    if not prefix:
        prefix = '$'
    return prefix

def separate_dice_and_name(inputs):
    """Sort the words of an input string, and identify which are dice notations and which are not."""

    dice = []
    words = []
    for input in inputs:
        if DICE_EXPRESSION.fullmatch(input):
            dice.append(Die(input))
        else:
            words.append(input.lower().capitalize())
    return {'dice': dice, 'name': ' '.join(words)}

def separate_numbers_and_name(inputs):
    """Sort the words of an input string, and identify which are numerals and which are not."""

    numbers = []
    words = []
    for input in inputs:
        if input.isdecimal():
            numbers.append(int(input))
        else:
            words.append(input.lower().capitalize())
    return {'numbers': numbers, 'name': ' '.join(words)}

def fetch_all_dice_for_parent(db_parent):
    """Given an object from the database, get all the dice that belong to it."""

    dice = []
    cursor.execute('SELECT * FROM DIE WHERE PARENT_GUID=:PARENT_GUID', {'PARENT_GUID':db_parent.db_guid})
    fetching = True
    while fetching:
        row = cursor.fetchone()
        if row:
            die = Die(name=row['NAME'], size=row['SIZE'], qty=row['QTY'])
            die.already_in_db(db_parent, row['GUID'])
            dice.append(die)
        else:
            fetching = False
    return dice

def purge():
    """Scan for old unused games and remove them."""

    logging.debug('Running the purge')
    purge_time = datetime.now(timezone.utc) - timedelta(days=PURGE_DAYS)
    games_to_purge = []
    cursor.execute('SELECT * FROM GAME WHERE ACTIVITY<:purge_time', {'purge_time':purge_time})
    fetching = True
    while fetching:
        row = cursor.fetchone()
        if row:
            games_to_purge.append(row['GUID'])
        else:
            fetching = False
    for game_guid in games_to_purge:
        cursor.execute('DELETE FROM GAME_OPTIONS WHERE PARENT_GUID=:guid', {'guid':game_guid})
        cursor.execute('SELECT * FROM DICE_COLLECTION WHERE PARENT_GUID=:guid', {'guid':game_guid})
        collections = []
        fetching = True
        while fetching:
            row = cursor.fetchone()
            if row:
                collections.append(row['GUID'])
            else:
                fetching = False
        for collection_guid in collections:
            cursor.execute('DELETE FROM DIE WHERE PARENT_GUID=:guid', {'guid':collection_guid})
        cursor.execute('DELETE FROM DIE WHERE PARENT_GUID=:guid', {'guid':game_guid})
        cursor.execute('DELETE FROM DICE_COLLECTION WHERE PARENT_GUID=:guid', {'guid':game_guid})
        cursor.execute('DELETE FROM RESOURCE WHERE PARENT_GUID=:guid', {'guid':game_guid})
        cursor.execute('DELETE FROM GAME WHERE GUID=:guid', {'guid':game_guid})
        db.commit()
    logging.debug('Deleted %d games', len(games_to_purge))

class Die:
    """A single die, or a set of dice of the same size."""

    def __init__(self, expression=None, name=None, size=4, qty=1):
        self.name = name
        self.size = size
        self.qty = qty
        self.db_parent = None
        self.db_guid = None
        if expression:
            if not DICE_EXPRESSION.fullmatch(expression):
                raise CortexError(DIE_STRING_ERROR, expression)
            numbers = expression.lower().split('d')
            if len(numbers) == 1:
                self.size = int(numbers[0])
            else:
                if numbers[0]:
                    self.qty = int(numbers[0])
                self.size = int(numbers[1])

    def store_in_db(self, db_parent):
        """Store this die in the database, under a given parent."""

        self.db_parent = db_parent
        self.db_guid = uuid.uuid1().hex
        cursor.execute('INSERT INTO DIE (GUID, NAME, SIZE, QTY, PARENT_GUID) VALUES (?, ?, ?, ?, ?)', (self.db_guid, self.name, self.size, self.qty, self.db_parent.db_guid))
        db.commit()

    def already_in_db(self, db_parent, db_guid):
        """Inform the Die that it is already in the database, under a given parent and guid."""

        self.db_parent = db_parent
        self.db_guid = db_guid

    def remove_from_db(self):
        """Remove this Die from the database."""

        if self.db_guid:
            cursor.execute('DELETE FROM DIE WHERE GUID=:guid', {'guid':self.db_guid})
            db.commit()

    def step_down(self):
        """Step down the die size."""

        if self.size > 4:
            self.update_size(self.size - 2)

    def step_up(self):
        """Step up the die size."""

        if self.size < 12:
            self.update_size(self.size + 2)

    def combine(self, other_die):
        """Combine this die with another die (as when applying a new stress die to existing stress)."""

        if self.size < other_die.size:
            self.update_size(other_die.size)
        elif self.size < 12:
            self.update_size(self.size + 2)

    def update_size(self, new_size):
        """Change the size of the die."""

        self.size = new_size
        if self.db_guid:
            cursor.execute('UPDATE DIE SET SIZE=:size WHERE GUID=:guid', {'size':self.size, 'guid':self.db_guid})
            db.commit()

    def update_qty(self, new_qty):
        """Change the quantity of the dice."""

        self.qty = new_qty
        if self.db_guid:
            cursor.execute('UPDATE DIE SET QTY=:qty WHERE GUID=:guid', {'qty':self.qty, 'guid':self.db_guid})

    def is_max(self):
        """Identify whether the Die is at the maximum allowed size."""

        return self.size == 12

    def output(self):
        """Return the Die as a string suitable for output in Discord."""

        return str(self)

    def __str__(self):
        """General purpose string representation of the Die."""

        if self.qty > 1:
            return '{0}D{1}'.format(self.qty, self.size)
        else:
            return 'D{0}'.format(self.size)

class NamedDice:
    """A collection of user-named single-die traits, suitable for complications and assets."""

    def __init__(self, category, group, db_parent, db_guid=None):
        self.dice = {}
        self.category = category
        self.group = group
        self.db_parent = db_parent
        if db_guid:
            self.db_guid = db_guid
        else:
            if self.group:
                cursor.execute('SELECT * FROM DICE_COLLECTION WHERE PARENT_GUID=:PARENT_GUID AND CATEGORY=:category AND GRP=:group', {'PARENT_GUID':self.db_parent.db_guid, 'category':self.category, 'group':self.group})
            else:
                cursor.execute('SELECT * FROM DICE_COLLECTION WHERE PARENT_GUID=:PARENT_GUID AND CATEGORY=:category AND GRP IS NULL', {'PARENT_GUID':self.db_parent.db_guid, 'category':self.category})
            row = cursor.fetchone()
            if row:
                self.db_guid = row['GUID']
            else:
                self.db_guid = uuid.uuid1().hex
                cursor.execute('INSERT INTO DICE_COLLECTION (GUID, CATEGORY, GRP, PARENT_GUID) VALUES (?, ?, ?, ?)', (self.db_guid, self.category, self.group, self.db_parent.db_guid))
                db.commit()
        fetched_dice = fetch_all_dice_for_parent(self)
        for die in fetched_dice:
            self.dice[die.name] = die

    def remove_from_db(self):
        """Remove these NamedDice from the database."""

        for name in list(self.dice):
            self.dice[name].remove_from_db()
        cursor.execute("DELETE FROM DICE_COLLECTION WHERE GUID=:db_guid", {'db_guid':self.db_guid})
        db.commit()
        self.dice = {}

    def is_empty(self):
        """Identify whether there are any dice in this object."""

        return not self.dice

    def add(self, name, die):
        """Add a new die, with a given name."""

        die.name = name
        if not name in self.dice:
            die.store_in_db(self)
            self.dice[name] = die
            return 'New: ' + self.output(name)
        elif self.dice[name].is_max():
            return 'This would step up beyond {0}'.format(self.output(name))
        else:
            self.dice[name].combine(die)
            return 'Raised to ' + self.output(name)

    def remove(self, name):
        """Remove a die with a given name."""

        if not name in self.dice:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        output = 'Removed: ' + self.output(name)
        self.dice[name].remove_from_db()
        del self.dice[name]
        return output

    def step_up(self, name):
        """Step up the die with a given name."""

        if not name in self.dice:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        if self.dice[name].is_max():
            return 'This would step up beyond {0}'.format(self.output(name))
        self.dice[name].step_up()
        return 'Stepped up to ' + self.output(name)

    def step_down(self, name):
        """Step down the die with a given name."""

        if not name in self.dice:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        if self.dice[name].size == 4:
            self.remove(name)
            return 'Stepped down and removed: ' + name
        else:
            self.dice[name].step_down()
            return 'Stepped down to ' + self.output(name)

    def get_all_names(self):
        """Identify the names of all the dice in this object."""

        return list(self.dice)

    def output(self, name):
        """For a die of a given name, return a formatted description of that die."""

        return '{0} {1}'.format(self.dice[name].output(), name)

    def output_all(self, separator='\n'):
        """Return a formatted description of all the dice in this object."""

        output = ''
        prefix = ''
        for name in list(self.dice):
            output += prefix + self.output(name)
            prefix = separator
        return output

class DicePool:
    """A single-purpose collection of die sizes and quantities, suitable for doom pools, crisis pools, and growth pools."""

    def __init__(self, roller, group, incoming_dice=[]):
        self.roller = roller
        self.group = group
        self.dice = [None, None, None, None, None]
        self.db_parent = None
        self.db_guid = None
        if incoming_dice:
            self.add(incoming_dice)

    def store_in_db(self, db_parent):
        """Store this pool in the database."""

        self.db_guid = uuid.uuid1().hex
        self.db_parent = db_parent
        logging.debug('going to store DicePool guid {0} grp {1} parent {2}'.format(self.db_guid, self.group, self.db_parent.db_guid))
        cursor.execute("INSERT INTO DICE_COLLECTION (GUID, CATEGORY, GRP, PARENT_GUID) VALUES (?, 'pool', ?, ?)", (self.db_guid, self.group, self.db_parent.db_guid))
        db.commit()

    def already_in_db(self, db_parent, db_guid):
        """Inform the pool that it is already in the database, under a given parent and guid."""

        self.db_parent = db_parent
        self.db_guid = db_guid

    def fetch_dice_from_db(self):
        """Get all the dice from the database that would belong to this pool."""

        fetched_dice = fetch_all_dice_for_parent(self)
        for die in fetched_dice:
            self.dice[DIE_SIZES.index(die.size)] = die

    def disconnect_from_db(self):
        """Prevent further changes to this pool from affecting the database."""

        self.db_parent = None
        self.db_guid = None

    def is_empty(self):
        """Identify whether this pool is empty."""

        return not self.dice

    def remove_from_db(self):
        """Remove this entire pool from the database."""

        for index in range(len(self.dice)):
            if self.dice[index]:
                self.dice[index].remove_from_db()
        cursor.execute("DELETE FROM DICE_COLLECTION WHERE GUID=:db_guid", {'db_guid':self.db_guid})
        db.commit()
        self.dice = [None, None, None, None, None]

    def add(self, dice):
        """Add dice to the pool."""

        for die in dice:
            index = DIE_SIZES.index(die.size)
            if self.dice[index]:
                self.dice[index].update_qty(self.dice[index].qty + die.qty)
            else:
                self.dice[index] = die
                if self.db_parent and not die.db_parent:
                    die.store_in_db(self)
        return self.output()

    def remove(self, dice):
        """Remove dice from the pool."""

        for die in dice:
            index = DIE_SIZES.index(die.size)
            if self.dice[index]:
                stored_die = self.dice[index]
                if die.qty > stored_die.qty:
                    raise CortexError(DIE_LACK_ERROR, stored_die.qty, stored_die.size)
                stored_die.update_qty(stored_die.qty - die.qty)
                if stored_die.qty == 0:
                    if self.db_parent:
                        stored_die.remove_from_db()
                    self.dice[index] = None
            else:
                raise CortexError(DIE_NONE_ERROR, die.size)
        return self.output()

    def temporary_copy(self):
        """Return a temporary, non-persisted copy of this dice pool."""
        copy = DicePool(self.roller, self.group)
        dice_copies = []
        for die in self.dice:
            if die:
                dice_copies.append(Die(size=die.size, qty=die.qty))
        copy.add(dice_copies)
        return copy

    def roll(self, suggest_best=False):
        """Roll all the dice in the pool, and return a formatted summary of the results."""

        output = ''
        separator = ''
        rolls = []
        for die in self.dice:
            if die:
                output += '{0}D{1} : '.format(separator, die.size)
                for num in range(die.qty):
                    roll = {'value': self.roller.roll(die.size), 'size': die.size}
                    roll_str = str(roll['value'])
                    if roll_str == '1':
                        roll_str = '**(1)**'
                    else:
                        rolls.append(roll)
                    output += roll_str + ' '
                separator = '\n'
        if suggest_best:
            if len(rolls) == 0:
                output += '\nBotch!'
            else:
                # Calculate best total, then choose an effect die
                rolls.sort(key=lambda roll: roll['value'], reverse=True)
                best_total_1 = rolls[0]['value']
                best_addition_1 = '{0}'.format(rolls[0]['value'])
                best_effect_1 = 'D4'
                if len(rolls) > 1:
                    best_total_1 += rolls[1]['value']
                    best_addition_1 = '{0} + {1}'.format(best_addition_1, rolls[1]['value'])
                    if len(rolls) > 2:
                        resorted_rolls = sorted(rolls[2:], key=lambda roll: roll['size'], reverse=True)
                        best_effect_1 = 'D{0}'.format(resorted_rolls[0]['size'])
                output += '\nBest Total: {0} ({1}) with Effect: {2}'.format(best_total_1, best_addition_1, best_effect_1)

                # Find best effect die, then chooose best total
                rolls.sort(key=lambda roll: roll['value'])
                rolls.sort(key=lambda roll: roll['size'], reverse=True)
                best_total_2 = rolls[0]['value']
                best_addition_2 = '{0}'.format(rolls[0]['value'])
                best_effect_2 = 'D4'
                if len(rolls) > 1:
                    best_total_2 += rolls[1]['value']
                    best_addition_2 = '{0} + {1}'.format(best_addition_2, rolls[1]['value'])
                    if len(rolls) > 2:
                        best_effect_2 = 'D{0}'.format(rolls[0]['size'])
                        resorted_rolls = sorted(rolls[1:], key=lambda roll: roll['value'], reverse=True)
                        best_total_2 = resorted_rolls[0]['value'] + resorted_rolls[1]['value']
                        best_addition_2 = '{0} + {1}'.format(resorted_rolls[0]['value'], resorted_rolls[1]['value'])
                if best_effect_1 != best_effect_1 or best_total_1 != best_total_2:
                    output += ' | Best Effect: {0} with Total: {1} ({2})'.format(best_effect_2, best_total_2, best_addition_2)
        return output

    def output(self):
        """Return a formatted list of the dice in this pool."""

        if self.is_empty():
            return 'empty'
        output = ''
        for die in self.dice:
            if die:
                output += die.output() + ' '
        return output

class DicePools:
    """A collection of DicePool objects."""

    def __init__(self, roller, db_parent):
        self.roller = roller
        self.pools = {}
        self.db_parent = db_parent
        cursor.execute('SELECT * FROM DICE_COLLECTION WHERE CATEGORY="pool" AND PARENT_GUID=:PARENT_GUID', {'PARENT_GUID':self.db_parent.db_guid})
        pool_info = []
        fetching = True
        while fetching:
            row = cursor.fetchone()
            if row:
                pool_info.append({'db_guid':row['GUID'], 'grp':row['GRP'], 'parent_guid':row['PARENT_GUID']})
            else:
                fetching = False
        for fetched_pool in pool_info:
            new_pool = DicePool(self.roller, fetched_pool['grp'])
            new_pool.already_in_db(fetched_pool['parent_guid'], fetched_pool['db_guid'])
            new_pool.fetch_dice_from_db()
            self.pools[new_pool.group] = new_pool

    def is_empty(self):
        """Identify whether we have any pools."""

        return not self.pools

    def remove_from_db(self):
        """Remove all of these pools from the database."""

        for group in list(self.pools):
            self.pools[group].remove_from_db()
        self.pools = {}

    def add(self, group, dice):
        """Add some dice to a pool under a given name."""

        if not group in self.pools:
            self.pools[group] = DicePool(self.roller, group)
            self.pools[group].store_in_db(self.db_parent)
        self.pools[group].add(dice)
        return '{0}: {1}'.format(group, self.pools[group].output())

    def remove(self, group, dice):
        """Remove some dice from a pool with a given name."""

        if not group in self.pools:
            raise CortexError(NOT_EXIST_ERROR, 'pool')
        self.pools[group].remove(dice)
        return '{0}: {1}'.format(group, self.pools[group].output())

    def clear(self, group):
        """Remove one entire pool."""
        if not group in self.pools:
            raise CortexError(NOT_EXIST_ERROR, 'pool')
        self.pools[group].remove_from_db()
        del self.pools[group]
        return 'Cleared {0} pool.'.format(group)

    def temporary_copy(self, group):
        """Return an independent, non-persistent copy of a pool."""

        if not group in self.pools:
            raise CortexError(NOT_EXIST_ERROR, 'pool')
        return self.pools[group].temporary_copy()

    def roll(self, group, suggest_best=False):
        """Roll all the dice in a certain pool and return the results."""

        return self.pools[group].roll(suggest_best)

    def output(self):
        """Return a formatted summary of all the pools in this object."""

        output = ''
        prefix = ''
        for key in list(self.pools):
            output += '{0}{1}: {2}'.format(prefix, key, self.pools[key].output())
            prefix = '\n'
        return output

class Resources:
    """Holds simple quantity-based resources, like plot points."""

    def __init__(self, category, db_parent):
        self.resources = {}
        self.category = category
        self.db_parent = db_parent
        cursor.execute("SELECT * FROM RESOURCE WHERE PARENT_GUID=:PARENT_GUID AND CATEGORY=:category", {'PARENT_GUID':self.db_parent.db_guid, 'category':self.category})
        fetching = True
        while fetching:
            row = cursor.fetchone()
            if row:
                self.resources[row['NAME']] = {'qty':row['QTY'], 'db_guid':row['GUID']}
            else:
                fetching = False

    def is_empty(self):
        """Identify whether there are any resources stored here."""

        return not self.resources

    def remove_from_db(self):
        """Removce these resources from the database."""

        cursor.executemany("DELETE FROM RESOURCE WHERE GUID=:db_guid", [{'db_guid':self.resources[resource]['db_guid']} for resource in list(self.resources)])
        db.commit()
        self.resources = {}

    def add(self, name, qty=1):
        """Add a quantity of resources to a given name."""

        if not name in self.resources:
            db_guid = uuid.uuid1().hex
            self.resources[name] = {'qty':qty, 'db_guid':db_guid}
            cursor.execute("INSERT INTO RESOURCE (GUID, CATEGORY, NAME, QTY, PARENT_GUID) VALUES (?, ?, ?, ?, ?)", (db_guid, self.category, name, qty, self.db_parent.db_guid))
            db.commit()
        else:
            self.resources[name]['qty'] += qty
            cursor.execute("UPDATE RESOURCE SET QTY=:qty WHERE GUID=:db_guid", {'qty':self.resources[name]['qty'], 'db_guid':self.resources[name]['db_guid']})
            db.commit()
        return self.output(name)

    def remove(self, name, qty=1):
        """Remove a quantity of resources from a given name."""

        if not name in self.resources:
            raise CortexError(HAS_NONE_ERROR, name, self.category)
        if self.resources[name]['qty'] < qty:
            raise CortexError(HAS_ONLY_ERROR, name, self.resources[name]['qty'], self.category)
        self.resources[name]['qty'] -= qty
        cursor.execute("UPDATE RESOURCE SET QTY=:qty WHERE GUID=:db_guid", {'qty':self.resources[name]['qty'], 'db_guid':self.resources[name]['db_guid']})
        db.commit()
        return self.output(name)

    def clear(self, name):
        """Remove a name from the catalog entirely."""
        if not name in self.resources:
            raise CortexError(HAS_NONE_ERROR, name, self.category)
        cursor.execute("DELETE FROM RESOURCE WHERE GUID=:db_guid", {'db_guid':self.resources[name]['db_guid']})
        db.commit()
        del self.resources[name]
        return 'Cleared {0} from {1} list.'.format(name, self.category)

    def output(self, name):
        """Return a formatted description of the resources held by a given name."""

        return '{0}: {1}'.format(name, self.resources[name]['qty'])

    def output_all(self):
        """Return a formatted summary of all resources."""

        output = ''
        prefix = ''
        for name in list(self.resources):
            output += prefix + self.output(name)
            prefix = '\n'
        return output

class GroupedNamedDice:
    """Holds named dice that are separated by groups, such as mental and physical stress (the dice names) assigned to characters (the dice groups)."""

    def __init__(self, category, db_parent):
        self.groups = {}
        self.category = category
        self.db_parent = db_parent
        cursor.execute("SELECT * FROM DICE_COLLECTION WHERE PARENT_GUID=:parent_guid AND CATEGORY=:category", {'parent_guid':self.db_parent.db_guid, 'category':self.category})
        group_guids = {}
        fetching = True
        while fetching:
            row = cursor.fetchone()
            if row:
                group_guids[row['GRP']] = row['GUID']
            else:
                fetching = False
        for group in group_guids:
            new_group = NamedDice(self.category, group, self.db_parent, db_guid=group_guids[group])
            self.groups[group] = new_group

    def is_empty(self):
        """Identifies whether we're holding any dice yet."""

        return not self.groups

    def remove_from_db(self):
        """Remove all of these dice from the database."""

        for group in list(self.groups):
            self.groups[group].remove_from_db()
        self.groups = {}

    def add(self, group, name, die):
        """Add dice with a given name to a given group."""

        if not group in self.groups:
            self.groups[group] = NamedDice(self.category, group, self.db_parent)
        return self.groups[group].add(name, die)

    def remove(self, group, name):
        """Remove dice with a given name from a given group."""

        if not group in self.groups:
            raise CortexError(HAS_NONE_ERROR, group, self.category)
        return self.groups[group].remove(name)

    def clear(self, group):
        """Remove all dice from a given group."""

        if not group in self.groups:
            raise CortexError(HAS_NONE_ERROR, group, self.category)
        self.groups[group].remove_from_db()
        del self.groups[group]
        return 'Cleared all {0} for {1}.'.format(self.category, group)

    def step_up(self, group, name):
        """Step up the die with a given name, within a given group."""

        if not group in self.groups:
            raise CortexError(HAS_NONE_ERROR, group, self.category)
        return self.groups[group].step_up(name)

    def step_down(self, group, name):
        """Step down the die with a given name, within a given group."""

        if not group in self.groups:
            raise CortexError(HAS_NONE_ERROR, group, self.category)
        return self.groups[group].step_down(name)

    def output(self, group):
        """Return a formatted list of all the dice within a given group."""

        if self.groups[group].is_empty():
            return '{0}: None'.format(group)
        return '{0}: {1}'.format(group, self.groups[group].output_all(separator=', '))

    def output_all(self):
        """Return a formatted summary of all dice under all groups."""

        output = ''
        prefix = ''
        for group in list(self.groups):
            output += prefix + self.output(group)
            prefix = '\n'
        return output

class CortexGame:
    """All information for a game, within a single server and channel."""

    def __init__(self, roller, server, channel):
        self.roller = roller
        self.pinned_message = None

        cursor.execute('SELECT * FROM GAME WHERE SERVER=:server AND CHANNEL=:channel', {"server":server, "channel":channel})
        row = cursor.fetchone()
        if not row:
            self.db_guid = uuid.uuid1().hex
            cursor.execute('INSERT INTO GAME (GUID, SERVER, CHANNEL, ACTIVITY) VALUES (?, ?, ?, ?)', (self.db_guid, server, channel, datetime.now(timezone.utc)))
            db.commit()
        else:
            self.db_guid = row['GUID']
        self.new()

    def new(self):
        """Set up new, empty traits for the game."""

        self.complications = NamedDice('complication', None, self)
        self.assets = NamedDice('asset', None, self)
        self.pools = DicePools(self.roller, self)
        self.plot_points = Resources('plot points', self)
        self.stress = GroupedNamedDice('stress', self)
        self.xp = Resources('xp', self)

    def clean(self):
        """Resets and erases the game's traits."""

        self.complications.remove_from_db()
        self.assets.remove_from_db()
        self.pools.remove_from_db()
        self.plot_points.remove_from_db()
        self.stress.remove_from_db()
        self.xp.remove_from_db()

    def output(self):
        """Return a report of all of the game's traits."""

        output = '**Cortex Game Information**\n'
        if not self.assets.is_empty():
            output += '\n**Assets**\n'
            output += self.assets.output_all()
            output += '\n'
        if not self.complications.is_empty():
            output += '\n**Complications**\n'
            output += self.complications.output_all()
            output += '\n'
        if not self.stress.is_empty():
            output += '\n**Stress**\n'
            output += self.stress.output_all()
            output += '\n'
        if not self.plot_points.is_empty():
            output += '\n**Plot Points**\n'
            output += self.plot_points.output_all()
            output += '\n'
        if not self.pools.is_empty():
            output += '\n**Dice Pools**\n'
            output += self.pools.output()
            output += '\n'
        if not self.xp.is_empty():
            output += '\n**Experience Points**\n'
            output += self.xp.output_all()
            output += '\n'
        return output

    def get_option(self, key):
        value = None
        cursor.execute('SELECT * FROM GAME_OPTIONS WHERE PARENT_GUID=:game_guid AND KEY=:key', {'game_guid':self.db_guid, 'key':key})
        row = cursor.fetchone()
        if row:
            value = row['VALUE']
        return value

    def get_option_as_bool(self, key):
        as_bool = False
        value_str = self.get_option(key)
        if value_str:
            if value_str == 'on':
                as_bool = True
        return as_bool

    def set_option(self, key, value):
        prior = self.get_option(key)
        if not prior:
            new_guid = uuid.uuid1().hex
            cursor.execute('INSERT INTO GAME_OPTIONS (GUID, KEY, VALUE, PARENT_GUID) VALUES (?, ?, ?, ?)', (new_guid, key, value, self.db_guid))
        else:
            cursor.execute('UPDATE GAME_OPTIONS SET VALUE=:value where KEY=:key and PARENT_GUID=:game_guid', {'value':value, 'key':key, 'game_guid':self.db_guid})
        db.commit()

    def update_activity(self):
        cursor.execute('UPDATE GAME SET ACTIVITY=:now WHERE GUID=:db_guid', {'now':datetime.now(timezone.utc), 'db_guid':self.db_guid})
        db.commit()

class Roller:
    """Generates random die rolls and remembers the frequency of results."""

    def __init__(self):
        self.results = {}
        for size in DIE_SIZES:
            self.results[size] = [0] * size

    def roll(self, size):
        """Roll a die of a given size and return the result."""

        face = random.SystemRandom().randrange(1, int(size) + 1)
        self.results[size][face - 1] += 1
        return face

    def output(self):
        """Return a report of die roll frequencies."""

        total = 0

        frequency = ''
        separator = ''
        for size in self.results:
            subtotal = sum(self.results[size])
            total += subtotal
            frequency += '**{0}D{1}** : {2} rolls'.format(separator, size, subtotal)
            separator = '\n'
            if subtotal > 0:
                for face in range(1, size + 1):
                    frequency += ' : **{0}** {1}x {2}%'.format(
                        face,
                        self.results[size][face - 1],
                        round(float(self.results[size][face - 1]) / float(subtotal) * 100.0, 1))

        output = (
        '**Randomness**\n'
        'The bot has rolled {0} dice since starting up.\n'
        '\n'
        'Roll frequency statistics:\n'
        '{1}'
        ).format(total, frequency)

        return output

class CortexPal(commands.Cog):
    """This cog encapsulates the commands and state of the bot."""

    def __init__(self, bot):
        """Initialize."""        
        self.bot = bot
        self.games = []
        self.startup_time = datetime.now(timezone.utc)
        self.last_command_time = None
        self.roller = Roller()

    def get_game_info(self, context):
        """Match a server and channel to a Cortex game."""
        game_info = None
        game_key = [context.guild.id, context.message.channel.id]
        for existing_game in self.games:
            if game_key == existing_game[0]:
                game_info = existing_game[1]
        if not game_info:
            game_info = CortexGame(self.roller, context.guild.id, context.message.channel.id)
            self.games.append([game_key, game_info])
        return game_info

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Intercepts any exceptions we haven't specifically caught elsewhere."""
        logging.error(error)
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(UNKNOWN_COMMAND_ERROR)
        else:
            await ctx.send(UNEXPECTED_ERROR)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        """After every command, determine whether we want to run a purge."""
        run_purge = False
        now = datetime.now(timezone.utc)
        if self.last_command_time:
            # Run purge after midnight
            if now.day != self.last_command_time.day:
                run_purge = True
        else:
            # Run purge on first command after startup
            run_purge = True
        if run_purge:
            purge()
            self.games = []
        self.last_command_time = now

    @commands.command()
    async def info(self, ctx):
        """Display all game information."""

        game = self.get_game_info(ctx)
        game.update_activity()
        await ctx.send(game.output())

    @commands.command()
    async def pin(self, ctx):
        """Pin a message to the channel to hold game information."""

        pins = await ctx.channel.pins()
        for pin in pins:
            if pin.author == self.bot.user:
                await pin.unpin()
        game = self.get_game_info(ctx)
        game.update_activity()
        game.pinned_message = await ctx.send(game.output())
        await game.pinned_message.pin()

    @commands.command()
    async def comp(self, ctx, *args):
        """
        Adjust complications.

        For example:
        $comp add 6 cloud of smoke (creates a D6 Cloud Of Smoke complication)
        $comp stepup confused (steps up the Confused complication)
        $comp stepdown dazed (steps down the Dazed complication)
        $comp remove sun in your eyes (removes the Sun In Your Eyes complication)
        """

        logging.info("comp command invoked")
        try:
            if not args:
                await ctx.send_help("comp")
            else:
                output = ''
                game = self.get_game_info(ctx)
                game.update_activity()
                separated = separate_dice_and_name(args[1:])
                dice = separated['dice']
                name = separated['name']
                update_pin = False
                if args[0] in ADD_SYNONYMS:
                    if not dice:
                        raise CortexError(DIE_MISSING_ERROR)
                    elif len(dice) > 1:
                        raise CortexError(DIE_EXCESS_ERROR)
                    elif dice[0].qty > 1:
                        raise CortexError(DIE_EXCESS_ERROR)
                    output = game.complications.add(name, dice[0])
                    update_pin = True
                elif args[0] in REMOVE_SYNOYMS:
                    output = game.complications.remove(name)
                    update_pin = True
                elif args[0] in UP_SYNONYMS:
                    output = game.complications.step_up(name)
                    update_pin = True
                elif args[0] in DOWN_SYNONYMS:
                    output = game.complications.step_down(name)
                    update_pin = True
                else:
                    raise CortexError(INSTRUCTION_ERROR, args[0], '$comp')
                if update_pin and game.pinned_message:
                    await game.pinned_message.edit(content=game.output())
                await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

    @commands.command()
    async def pp(self, ctx, *args):
        """
        Adjust plot points.

        For example:
        $pp add alice 3 (gives Alice 3 plot points)
        $pp remove alice (spends one of Alice's plot points)
        $pp clear alice (clears Alice from plot point lists)
        """

        logging.info("pp command invoked")
        try:
            if not args:
                await ctx.send_help("pp")
            else:
                output = ''
                update_pin = False
                game = self.get_game_info(ctx)
                game.update_activity()
                separated = separate_numbers_and_name(args[1:])
                name = separated['name']
                qty = 1
                if separated['numbers']:
                    qty = separated['numbers'][0]
                if args[0] in ADD_SYNONYMS:
                    output = 'Plot points for ' + game.plot_points.add(name, qty)
                    update_pin = True
                elif args[0] in REMOVE_SYNOYMS:
                    output = 'Plot points for ' + game.plot_points.remove(name, qty)
                    update_pin = True
                elif args[0] in CLEAR_SYNONYMS:
                    output = game.plot_points.clear(name)
                    update_pin = True
                else:
                    raise CortexError(INSTRUCTION_ERROR, args[0], '$pp')
                if update_pin and game.pinned_message:
                    await game.pinned_message.edit(content=game.output())
                await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

    @commands.command()
    async def roll(self, ctx, *args):
        """
        Roll some dice.

        For example:
        $roll 12 (rolls a D12)
        $roll 4 3d8 10 10 (rolls a D4, 3D8, and 2D10)

        You may include your trait names. The command will ignore any words that don't look like dice.

        For example:
        $roll D6 Mind D10 Navigation D6 Pirate (rolls 2D6 and a D10, ignoring the trait names)
        """

        logging.info("roll command invoked")
        results = {}
        try:
            if not args:
                await ctx.send_help("roll")
            else:
                game = self.get_game_info(ctx)
                suggest_best = game.get_option_as_bool(BEST_OPTION)
                separated = separate_dice_and_name(args)
                ignored_strings = separated['name']
                dice = separated['dice']
                """
                ignored_line = ''
                if ignored_strings:
                    ignored_line = '\n*Ignored: {0}*'.format(ignored_strings)
                """
                pool = DicePool(self.roller, None, incoming_dice=dice)
                echo_line = 'Rolling: {0}\n'.format(pool.output())
                await ctx.send(echo_line + pool.roll(suggest_best))
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

    @commands.command()
    async def pool(self, ctx, *args):
        """
        Adjust dice pools.

        For example:
        $pool add doom 6 2d8 (gives the Doom pool a D6 and 2D8)
        $pool remove doom 10 (spends a D10 from the Doom pool)
        $pool roll doom (rolls the Doom pool)
        $pool roll doom 2d6 10 (rolls the Doom pool and adds 2D6 and a D10)
        $pool clear doom (clears the entire Doom pool)
        """

        logging.info("pool command invoked")
        try:
            if not args:
                await ctx.send_help("pool")
            else:
                output = ''
                update_pin = False
                game = self.get_game_info(ctx)
                game.update_activity()
                suggest_best = game.get_option_as_bool(BEST_OPTION)
                separated = separate_dice_and_name(args[1:])
                dice = separated['dice']
                name = separated['name']
                if args[0] in ADD_SYNONYMS:
                    output = game.pools.add(name, dice)
                    update_pin = True
                elif args[0] in REMOVE_SYNOYMS:
                    output = game.pools.remove(name, dice)
                    update_pin = True
                elif args[0] in CLEAR_SYNONYMS:
                    output = game.pools.clear(name)
                    update_pin = True
                elif args[0] == 'roll':
                    temp_pool = game.pools.temporary_copy(name)
                    temp_pool.add(dice)
                    output = temp_pool.roll(suggest_best)
                else:
                    raise CortexError(INSTRUCTION_ERROR, args[0], '$pool')
                if update_pin and game.pinned_message:
                    await game.pinned_message.edit(content=game.output())
                await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

    @commands.command()
    async def stress(self, ctx, *args):
        """
        Adjust stress.

        For example:
        $stress add amy 8 (gives Amy D8 general stress)
        $stress add ben mental 6 (gives Ben D6 Mental stress)
        $stress stepup cat social (steps up Cat's Social stress)
        $stress stepdown doe physical (steps down Doe's Physical stress)
        $stress remove eve psychic (removes Eve's Psychic stress)
        $stress clear fin (clears all of Fin's stress)
        """

        logging.info("stress command invoked")
        try:
            if not args:
                await ctx.send_help("stress")
            else:
                output = ''
                update_pin = False
                game = self.get_game_info(ctx)
                game.update_activity()
                separated = separate_dice_and_name(args[1:])
                dice = separated['dice']
                split_name = separated['name'].split(' ', maxsplit=1)
                owner_name = split_name[0]
                if len(split_name) == 1:
                    stress_name = UNTYPED_STRESS
                else:
                    stress_name = split_name[1]
                if args[0] in ADD_SYNONYMS:
                    if not dice:
                        raise CortexError(DIE_MISSING_ERROR)
                    elif len(dice) > 1:
                        raise CortexError(DIE_EXCESS_ERROR)
                    elif dice[0].qty > 1:
                        raise CortexError(DIE_EXCESS_ERROR)
                    output = '{0} Stress for {1}'.format(game.stress.add(owner_name, stress_name, dice[0]), owner_name)
                    update_pin = True
                elif args[0] in REMOVE_SYNOYMS:
                    output = '{0} Stress for {1}'.format(game.stress.remove(owner_name, stress_name), owner_name)
                    update_pin = True
                elif args[0] in UP_SYNONYMS:
                    output = '{0} Stress for {1}'.format(game.stress.step_up(owner_name, stress_name), owner_name)
                    update_pin = True
                elif args[0] in DOWN_SYNONYMS:
                    output = '{0} Stress for {1}'.format(game.stress.step_down(owner_name, stress_name), owner_name)
                    update_pin = True
                elif args[0] in CLEAR_SYNONYMS:
                    output = game.stress.clear(owner_name)
                    update_pin = True
                else:
                    raise CortexError(INSTRUCTION_ERROR, args[0], '$stress')
                if update_pin and game.pinned_message:
                    await game.pinned_message.edit(content=game.output())
                await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

    @commands.command()
    async def asset(self, ctx, *args):
        """
        Adjust assets.

        For example:
        $asset add 6 big wrench (adds a D6 Big Wrench asset)
        $asset stepup fast car (steps up the Fast Car asset)
        $asset stepdown nice outfit (steps down the Nice Outfit asset)
        $asset remove jetpack (removes the Jetpack asset)
        """

        logging.info("asset command invoked")
        output = ''
        try:
            if not args:
                await ctx.send_help("asset")
            else:
                output = ''
                game = self.get_game_info(ctx)
                game.update_activity()
                separated = separate_dice_and_name(args[1:])
                dice = separated['dice']
                name = separated['name']
                update_pin = False
                if args[0] in ADD_SYNONYMS:
                    if not dice:
                        raise CortexError(DIE_MISSING_ERROR)
                    elif len(dice) > 1:
                        raise CortexError(DIE_EXCESS_ERROR)
                    elif dice[0].qty > 1:
                        raise CortexError(DIE_EXCESS_ERROR)
                    output = game.assets.add(name, dice[0])
                    update_pin = True
                elif args[0] in REMOVE_SYNOYMS:
                    output = game.assets.remove(name)
                    update_pin = True
                elif args[0] in UP_SYNONYMS:
                    output = game.assets.step_up(name)
                    update_pin = True
                elif args[0] in DOWN_SYNONYMS:
                    output = game.assets.step_down(name)
                    update_pin = True
                else:
                    raise CortexError(INSTRUCTION_ERROR, args[0], '$asset')
                if update_pin and game.pinned_message:
                    await game.pinned_message.edit(content=game.output())
                await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

    @commands.command()
    async def xp(self, ctx, *args):
        """
        Award experience points.

        For example:
        $xp add alice 3 (gives Alice 3 experience points)
        $xp remove alice (spends one of Alice's experience points)
        $xp clear alice (clears Alice from experience point lists)
        """

        logging.info("xp command invoked")
        try:
            if not args:
                await ctx.send_help("xp")
            else:
                output = ''
                update_pin = False
                game = self.get_game_info(ctx)
                game.update_activity()
                separated = separate_numbers_and_name(args[1:])
                name = separated['name']
                qty = 1
                if separated['numbers']:
                    qty = separated['numbers'][0]
                if args[0] in ADD_SYNONYMS:
                    output = 'Experience points for ' + game.xp.add(name, qty)
                    update_pin = True
                elif args[0] in REMOVE_SYNOYMS:
                    output = 'Experience points for ' + game.xp.remove(name, qty)
                    update_pin = True
                elif args[0] in CLEAR_SYNONYMS:
                    output = game.xp.clear(name)
                    update_pin = True
                else:
                    raise CortexError(INSTRUCTION_ERROR, args[0], '$xp')
                if update_pin and game.pinned_message:
                    await game.pinned_message.edit(content=game.output())
                await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

    @commands.command()
    async def clean(self, ctx):
        """
        Reset all game data for a channel.
        """

        logging.info("clean command invoked")
        try:
            game = self.get_game_info(ctx)
            game.update_activity()
            game.clean()
            if game.pinned_message:
                await game.pinned_message.edit(content=game.output())
            await ctx.send('Cleaned up all game information.')
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

    @commands.command()
    async def report(self, ctx):
        """
        Report the bot's statistics.
        """

        start_formatted = self.startup_time.isoformat(sep=' ', timespec='seconds')
        last_formatted = '(no user commands yet)'
        if self.last_command_time:
            last_formatted = self.last_command_time.isoformat(sep=' ', timespec='seconds')

        output = (
        '**CortexPal Usage Report**\n'
        'Bot started up at UTC {0}.\n'
        'Last user command was at UTC {1}.\n'
        '\n'
        ).format(start_formatted, last_formatted)

        output += self.roller.output()
        await ctx.send(output)

    @commands.command()
    async def option(self, ctx, *args):
        """
        Change the bot's optional behavior.

        For example:
        $option prefix ! (change the command prefix to ! instead of $)
        $option best on (turn on suggestions for best total and effect)
        $option best off (turn off suggestions for best total and effect)
        """
        game = self.get_game_info(ctx)
        game.update_activity()
        output = 'No such option.'

        try:
            if not args:
                await ctx.send_help("option")
            else:
                if args[0] == PREFIX_OPTION:
                    if len(args[1]) > 1:
                        output = 'Prefix must be a single character.'
                    else:
                        game.set_option(PREFIX_OPTION, args[1])
                        output = 'Prefix set to {0}'.format(args[1])
                elif args[0] == BEST_OPTION:
                    if args[1] == 'on' or args[1] == 'off':
                        game.set_option(BEST_OPTION, args[1])
                        output = 'Option to suggest best total and effect is now {0}.'.format(args[1])
                    else:
                        output = 'You may only set this option to "on" or "off".'
                await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

# Set up bot.

TOKEN = config['discord']['token']
bot = commands.Bot(command_prefix=get_prefix, description=ABOUT_TEXT)

# Start the bot.

logging.info("Bot startup")
bot.add_cog(CortexPal(bot))
bot.run(TOKEN)
