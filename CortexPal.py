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
from discord.ext import commands
from datetime import datetime

PREFIX = '$'

DICE_EXPRESSION = re.compile('(\d*(d|D))?(4|6|8|10|12)')
DIE_SIZES = [4, 6, 8, 10, 12]

UNTYPED_STRESS = 'General'

ADD_SYNONYMS = ['add', 'give', 'new', 'create']
REMOVE_SYNOYMS = ['remove', 'spend', 'delete', 'subtract']
UP_SYNONYMS = ['stepup', 'up']
DOWN_SYNONYMS = ['stepdown', 'down']

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
UNEXPECTED_ERROR = 'Oops. A software error interrupted this command.'

ABOUT_TEXT = 'CortexPal v0.2: a Discord bot for Cortex Prime RPG players.'

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
'CHANNEL INT NOT NULL)'
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

# Set up bot.

TOKEN = config['discord']['token']
bot = commands.Bot(command_prefix='$', description=ABOUT_TEXT)

# Classes and functions follow.

class CortexError(Exception):
    def __init__(self, message, *args):
        self.message = message
        self.args = args

    def __str__(self):
        return self.message.format(*(self.args))

def separate_dice_and_name(inputs):
    dice = []
    words = []
    for input in inputs:
        if DICE_EXPRESSION.fullmatch(input):
            dice.append(Die(input))
        else:
            words.append(input.lower().capitalize())
    return {'dice': dice, 'name': ' '.join(words)}

def separate_numbers_and_name(inputs):
    numbers = []
    words = []
    for input in inputs:
        if input.isdecimal():
            numbers.append(int(input))
        else:
            words.append(input.lower().capitalize())
    return {'numbers': numbers, 'name': ' '.join(words)}

def fetch_all_dice_for_parent(db_parent):
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

class Die:
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
        self.db_parent = db_parent
        self.db_guid = uuid.uuid1().hex
        cursor.execute('INSERT INTO DIE (GUID, NAME, SIZE, QTY, PARENT_GUID) VALUES (?, ?, ?, ?, ?)', (self.db_guid, self.name, self.size, self.qty, self.db_parent.db_guid))
        db.commit()

    def already_in_db(self, db_parent, db_guid):
        self.db_parent = db_parent
        self.db_guid = uuid.uuid1().hex

    def remove_from_db(self):
        if self.db_guid:
            cursor.execute('DELETE FROM DIE WHERE GUID=:guid', {'guid':self.db_guid})

    def step_down(self):
        if self.size > 4:
            self.update_size(self.size - 2)

    def step_up(self):
        if self.size < 12:
            self.update_size(self.size + 2)

    def combine(self, other_die):
        if self.size < other_die.size:
            self.update_size(other_die.size)
        elif self.size < 12:
            self.update_size(self.size + 2)

    def update_size(self, new_size):
        self.size = new_size
        if self.db_guid:
            cursor.execute('UPDATE DIE SET SIZE=:size WHERE GUID=:guid', {'size':self.size, 'guid':self.db_guid})
            db.commit()

    def update_qty(self, new_qty):
        self.qty = new_qty
        if self.db_guid:
            cursor.execute('UPDATE DIE SET QTY=:qty WHERE GUID=:guid', {'qty':self.qty, 'guid':self.db_guid})

    def is_max(self):
        return self.size == 12

    def output(self):
        if self.qty > 1:
            return '{0}D{1}'.format(self.qty, self.size)
        else:
            return 'D{0}'.format(self.size)

"""
NamedDice: a collection of user-named single-die traits.
Suitable for complications and assets.
"""
class NamedDice:
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
        cursor.execute("DELETE FROM DICE_COLLECTION WHERE GUID=:db_guid", {'guid':self.db_guid})
        db.commit()

    def is_empty(self):
        return not self.dice

    def add(self, name, die):
        die.name = name
        if not name in self.dice:
            die.store_in_db(self)
            self.dice[name] = die
            return 'New: ' + self.output(name)
        elif self.dice[name].is_max():
            return 'This would step up beyond {0}'.format(self.output(name))
        else:
            self.dice[name].combine(die)
            return 'Raised: ' + self.output(name)

    def remove(self, name):
        if not name in self.dice:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        output = 'Removed: ' + self.output(name)
        self.dice[name].remove_from_db()
        del self.dice[name]
        return output

    def step_up(self, name):
        if not name in self.dice:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        if self.dice[name].is_max():
            return 'This would step up beyond {0}'.format(self.output(name))
        self.dice[name].step_up()
        return 'Stepped up: ' + self.output(name)

    def step_down(self, name):
        if not name in self.dice:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        if self.dice[name].qty == 4:
            self.remove(name)
            return 'Stepped down and removed: ' + name
        else:
            self.dice[name].step_down()
            return 'Stepped down: ' + self.output(name)

    def get_all_names(self):
        return list(self.dice)

    def output(self, name):
        return '{0} {1}'.format(self.dice[name].output(), name)

    def output_all(self, separator='\n'):
        output = ''
        prefix = ''
        for name in list(self.dice):
            output += prefix + self.output(name)
            prefix = separator
        return output

"""
DicePool: a single-purpose collection of die sizes and quantities.
Suitable for doom pools, crisis pools, and growth pools.
Not necessarily persisted in the database.
"""
class DicePool:
    def __init__(self, roller, group, incoming_dice=[]):
        self.roller = roller
        self.group = group
        self.dice = [None, None, None, None, None]
        self.db_parent = None
        self.db_guid = None
        if incoming_dice:
            self.add(incoming_dice)

    def store_in_db(self, db_parent):
        self.db_guid = uuid.uuid1().hex
        self.db_parent = db_parent
        cursor.execute("INSERT INTO DICE_COLLECTION (GUID, CATEGORY, GRP, PARENT_GUID) VALUES (?, 'pool', ?, ?)", (self.db_guid, self.group, self.db_parent.db_guid))
        db.commit()

    def already_in_db(self, db_parent, db_guid):
        self.db_parent = db_parent
        self.db_guid = db_guid

    def fetch_dice_from_db(self):
        fetched_dice = fetch_all_dice_for_parent(self)
        for die in fetched_dice:
            self.dice[DIE_SIZES.index(die.size)] = die

    def is_empty(self):
        return not self.dice

    def add(self, dice):
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

    def roll(self):
        output = ''
        separator = ''
        for die in self.dice:
            if die:
                output += '{0}D{1} : '.format(separator, die.size)
                for num in range(die.qty):
                    roll = str(self.roller.roll(die.size))
                    if roll == '1':
                        roll = '**(1)**'
                    output += roll + ' '
                separator = '\n'
        return output

    def output(self):
        if self.is_empty():
            return 'empty'
        output = ''
        for die in self.dice:
            if die:
                output += die.output() + ' '
        return output

class DicePools:
    def __init__(self, roller, db_parent):
        self.roller = roller
        self.pools = {}
        self.db_parent = db_parent
        cursor.execute('SELECT * FROM DICE_COLLECTION WHERE CATEGORY="pool" AND PARENT_GUID=:PARENT_GUID', {'PARENT_GUID':self.db_parent.db_guid})
        fetching = True
        while fetching:
            row = cursor.fetchone()
            if row:
                new_pool = DicePool(self.roller, row['GRP'])
                new_pool.already_in_db(row['PARENT_GUID'], row['GUID'])
                new_pool.fetch_dice_from_db()
                self.pools[new_pool.group] = new_pool
            else:
                fetching = False

    def is_empty(self):
        return not self.pools

    def add(self, group, dice):
        if not group in self.pools:
            self.pools[group] = DicePool(self.roller, group)
            self.pools[group].store_in_db(self.db_parent)
        self.pools[group].add(dice)
        return '{0}: {1}'.format(group, self.pools[group].output())

    def remove(self, group, dice):
        if not group in self.pools:
            raise CortexError(NOT_EXIST_ERROR, 'pool')
        self.pools[group].remove(dice)
        return '{0}: {1}'.format(group, self.pools[group].output())

    def roll(self, group):
        return self.pools[group].roll()

    def output(self):
        output = ''
        prefix = ''
        for key in list(self.pools):
            output += '{0}{1}: {2}'.format(prefix, key, self.pools[key].output())
            prefix = '\n'
        return output

class Resources:
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
        return not self.resources

    def add(self, name, qty=1):
        if not name in self.resources:
            db_guid = uuid.uuid1().hex
            self.resources[name] = {'qty':qty, 'db_guid':db_guid}
            cursor.execute("INSERT INTO RESOURCE (GUID, CATEGORY, NAME, QTY, PARENT_GUID) VALUES (?, ?, ?, ?, ?)", (db_guid, self.category, name, qty, self.db_parent.db_guid))
            db.commit()
        else:
            self.resources[name]['qty'] += qty
            cursor.execute("UPDATE RESOURCE SET QTY=:qty WHERE GUID=:db_guid", {'qty':self.resources[name][qty], 'guid':self.resources[name][db_guid]})
            db.commit()
        return self.output(name)

    def remove(self, name, qty=1):
        if not name in self.resources:
            raise CortexError(HAS_NONE_ERROR, name, self.category)
        if self.resources[name]['qty'] < qty:
            raise CortexError(HAS_ONLY_ERROR, name, self.resources[name]['qty'], self.category)
        self.resources[name]['qty'] -= qty
        cursor.execute("UPDATE RESOURCE SET QTY=:qty WHERE GUID=:db_guid", {'qty':self.resources[name]['qty'], 'guid':self.resources[name]['db_guid']})
        db.commit()
        return self.output(name)

    def output(self, name):
        return '{0}: {1}'.format(name, self.resources[name]['qty'])

    def output_all(self):
        output = ''
        prefix = ''
        for name in list(self.resources):
            output += prefix + self.output(name)
            prefix = '\n'
        return output

class GroupedNamedDice:
    def __init__(self, category, db_parent):
        self.groups = {}
        self.category = category
        self.db_parent = db_parent
        cursor.execute("SELECT * FROM DICE_COLLECTION WHERE PARENT_GUID=:PARENT_GUID AND CATEGORY=:category", {'PARENT_GUID':self.db_parent.db_guid, 'category':self.category})
        fetching = True
        while fetching:
            row = cursor.fetchone()
            if row:
                new_group = NamedDice(self.category, row['GRP'], self.db_parent, db_guid=row['GUID'])
                self.groups[row['GRP']] = new_group
            else:
                fetching = False

    def is_empty(self):
        return not self.groups

    def add(self, group, name, die):
        if not group in self.groups:
            self.groups[group] = NamedDice(self.category, group, self.db_parent)
        return self.groups[group].add(name, die)

    def remove(self, group, name):
        if not group in self.groups:
            raise CortexError(HAS_NONE_ERROR, group, self.category)
        return self.groups[group].remove(name)

    def step_up(self, group, name):
        if not group in self.groups:
            raise CortexError(HAS_NONE_ERROR, group, self.category)
        return self.groups[group].step_up(name)

    def step_down(self, group, name):
        if not group in self.groups:
            raise CortexError(HAS_NONE_ERROR, group, self.category)
        return self.groups[group].step_down(name)

    def get_all_names(self):
        return list(self.dice)

    def output(self, group):
        if self.groups[group].is_empty():
            return '{0}: None'.format(group)
        return '{0}: {1}'.format(group, self.groups[group].output_all(separator=', '))

    def output_all(self):
        output = ''
        prefix = ''
        for group in list(self.groups):
            output += prefix + self.output(group)
            prefix = '\n'
        return output

class CortexGame:
    def __init__(self, roller, server, channel):
        self.roller = roller
        self.pinned_message = None

        cursor.execute('SELECT * FROM GAME WHERE SERVER=:server AND CHANNEL=:channel', {"server":server, "channel":channel})
        row = cursor.fetchone()
        if not row:
            self.db_guid = uuid.uuid1().hex
            cursor.execute('INSERT INTO GAME (GUID, SERVER, CHANNEL) VALUES (?, ?, ?)', (self.db_guid, server, channel))
            db.commit()
        else:
            self.db_guid = row['GUID']

        self.complications = NamedDice('complication', None, self)
        self.assets = NamedDice('asset', None, self)
        self.pools = DicePools(self.roller, self)
        self.plot_points = Resources('plot points', self)
        self.stress = GroupedNamedDice('stress', self)

    def clean(self):
        self.complications = NamedDice('complication')
        self.plot_points = Resources('plot points')
        self.pools = DicePools(self.roller)
        self.stress = GroupedNamedDice('stress')
        self.assets = NamedDice('asset')

    def output(self):
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
        return output

class Roller:
    def __init__(self):
        self.results = {}
        for size in DIE_SIZES:
            self.results[size] = [0] * size

    def roll(self, size):
        face = random.SystemRandom().randrange(1, int(size) + 1)
        self.results[size][face - 1] += 1
        return face

    def output(self):
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
    def __init__(self, bot):
        self.bot = bot
        self.games = []
        self.startup_time = datetime.utcnow()
        self.last_command_time = None
        self.roller = Roller()

    def update_command_time(self):
        self.last_command_time = datetime.utcnow()

    def get_game_info(self, context):
        game_info = None
        game_key = [context.guild.id, context.message.channel.id]
        for existing_game in self.games:
            if game_key == existing_game[0]:
                game_info = existing_game[1]
        if not game_info:
            game_info = CortexGame(self.roller, context.guild.id, context.message.channel.id)
            self.games.append([game_key, game_info])
        return game_info

    """
    def cog_command_error(self, ctx, error):
        logging.error(error)

    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        logging.error(traceback.format_exc())
    """

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        logging.error(error)

    @commands.command()
    async def info(self, ctx):
        """Display all game information."""

        self.update_command_time()
        game = self.get_game_info(ctx)
        await ctx.send(game.output())

    @commands.command()
    async def pin(self, ctx):
        """Pin a message to the channel to hold game information."""

        self.update_command_time()
        pins = await ctx.channel.pins()
        for pin in pins:
            if pin.author == self.bot.user:
                await pin.unpin()
        game = self.get_game_info(ctx)
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
        self.update_command_time()
        try:
            if not args:
                await ctx.send_help("comp")
            else:
                output = ''
                game = self.get_game_info(ctx)
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
        """

        logging.info("pp command invoked")
        self.update_command_time()
        try:
            if not args:
                await ctx.send_help("pp")
            else:
                output = ''
                update_pin = False
                game = self.get_game_info(ctx)
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
        """

        logging.info("roll command invoked")
        self.update_command_time()
        results = {}
        try:
            if not args:
                await ctx.send_help("roll")
            else:
                separated = separate_dice_and_name(args)
                invalid_strings = separated['name']
                dice = separated['dice']
                if invalid_strings:
                    raise CortexError(DIE_STRING_ERROR, invalid_strings)
                pool = DicePool(self.roller, dice)
                await ctx.send(pool.roll())
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
        """

        logging.info("pool command invoked")
        self.update_command_time()
        try:
            if not args:
                await ctx.send_help("pool")
            else:
                output = ''
                update_pin = False
                game = self.get_game_info(ctx)
                separated = separate_dice_and_name(args[1:])
                dice = separated['dice']
                name = separated['name']
                if args[0] in ADD_SYNONYMS:
                    output = game.pools.add(name, dice)
                    update_pin = True
                elif args[0] in REMOVE_SYNOYMS:
                    output = game.pools.remove(name, dice)
                    update_pin = True
                elif args[0] == 'roll':
                    output = game.pools.roll(name)
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
        """

        logging.info("stress command invoked")
        self.update_command_time()
        try:
            if not args:
                await ctx.send_help("stress")
            else:
                output = ''
                update_pin = False
                game = self.get_game_info(ctx)
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
        self.update_command_time()
        output = ''
        try:
            if not args:
                await ctx.send_help("asset")
            else:
                output = ''
                game = self.get_game_info(ctx)
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
    async def clean(self, ctx):
        """
        Reset all game data for a channel.
        """

        logging.info("clean command invoked")
        self.update_command_time()
        try:
            game = self.get_game_info(ctx)
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


# Start the bot.

logging.info("Bot startup")
bot.add_cog(CortexPal(bot))
bot.run(TOKEN)
