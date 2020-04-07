import discord
import random
import os
import traceback
import re
import logging
import configparser
from discord.ext import commands

PREFIX = '$'

UNTYPED_STRESS = 'General'

ADD_SYNONYMS = ['add', 'give', 'new']
REMOVE_SYNOYMS = ['remove', 'spend', 'delete', 'subtract']

DICE_EXPRESSION = re.compile('(\d*(d|D))?(4|6|8|10|12)')
DIE_SIZES = [4, 6, 8, 10, 12]

DIE_FACE_ERROR = '{0} is not a valid die size. You may only use dice with sizes of 4, 6, 8, 10, or 12.'
DIE_STRING_ERROR = '{0} is not a valid die or dice.'
DIE_EXCESS_ERROR = 'You can\'t use that many dice.'
DIE_MISSING_ERROR = 'There were no valid dice in that command.'
DIE_LACK_ERROR = 'That pool only has {0}D{1}.'
DIE_NONE_ERROR = 'That pool doesn\'t have any D{0}s.'
NOT_EXIST_ERROR = 'That {0} doesn\'t exist yet.'
HAS_NONE_ERROR = '{0} doesn\'t have any {1}.'
HAS_ONLY_ERROR = '{0} only has {1} {2}.'
UNEXPECTED_ERROR = 'Oops. A software error interrupted this command.'

config = configparser.ConfigParser()
config.read('cortexpal.ini')
logging.basicConfig(filename=config['logging']['file'], format='%(asctime)s %(message)s', level=logging.INFO)
TOKEN = config['discord']['token']
bot = commands.Bot(command_prefix='$')

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

def clean_up_key(typed_key):
    return ' '.join([word.lower().capitalize() for word in typed_key.split(' ')])

def find_die_error(die):
    error = None
    if not die in ['4', '6', '8', '10', '12']:
        raise CortexError(DIE_FACE_ERROR, die)

class Die:
    def __init__(self, expression):
        self.size = 4
        self.qty = 1
        if not DICE_EXPRESSION.fullmatch(expression):
            raise CortexError(DIE_STRING_ERROR, expression)
        numbers = expression.lower().split('d')
        if len(numbers) == 1:
            self.size = int(numbers[0])
        else:
            if numbers[0]:
                self.qty = int(numbers[0])
            self.size = int(numbers[1])

    def step_down(self):
        if self.size > 4:
            self.size -= 2

    def step_up(self):
        if self.size < 12:
            self.size += 2

    def combine(self, other_die):
        if self.size < other_die.size:
            self.size = other_die.size
        elif self.size < 12:
            self.size += 2

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
    def __init__(self, category):
        self.dice = {}
        self.category = category

    def is_empty(self):
        return not self.dice

    def add(self, name, die):
        if not name in self.dice:
            self.dice[name] = die
            return 'New: ' + self.output(name)
        else:
            self.dice[name].combine(die)
            return 'Raised ' + self.output(name)

    def step_up(self, name):
        if not name in self.dice:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        self.dice[name].step_up()
        return 'Stepped up: ' + self.output(name)

    def step_down(self, name):
        if not name in self.dice:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        if self.dice[name].qty == 4:
            del self.dice[name]
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

class DicePool:
    def __init__(self, incoming_dice=[]):
        self.dice = [None, None, None, None, None]
        for die in incoming_dice:
            self.add(die)

    def is_empty(self):
        return not self.dice

    def add(self, die):
        index = DIE_SIZES.index(die.size)
        if self.dice[index]:
            self.dice[index].qty += die.qty
        else:
            self.dice[index] = die
        return self.output()

    def remove(self, die):
        index = DIE_SIZES.index(die.size)
        if self.dice[index]:
            stored_die = self.dice[index]
            if die.qty > stored_die.qty:
                raise CortexError(DIE_LACK_ERROR, stored_die.qty, stored_die.size)
            stored_die.qty -= die.qty
            if stored_die.qty == 0:
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
                    roll = str(random.SystemRandom().randrange(1, int(die.size) + 1))
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
    def __init__(self):
        self.pools = {}

    def is_empty(self):
        return not self.pools

    def add(self, name, size, qty=1):
        key = clean_up_key(name)
        if not key in self.pools:
            self.pools[key] = DicePool()
        output = self.pools[key].add(size, qty)
        return '{0}: {1}'.format(key, output)

    def remove(self, name, size, qty=1):
        key = clean_up_key(name)
        output = self.pools[key].remove(size, qty)
        return '{0}: {1}'.format(key, output)

    def roll(self, name):
        key = clean_up_key(name)
        return self.pools[key].roll()

    def output(self):
        output = ''
        prefix = ''
        for key in list(self.pools):
            output += '{0}{1}: {2}'.format(prefix, key, self.pools[key].output())
            prefix = '\n'
        return output

class Resources:
    def __init__(self, category):
        self.resources = {}
        self.category = category

    def is_empty(self):
        return not self.resources

    def add(self, name, qty=1):
        key = clean_up_key(name)
        if not key in self.resources:
            self.resources[key] = qty
        else:
            self.resources[key] += qty
        return self.output(key)

    def remove(self, name, qty=1):
        key = clean_up_key(name)
        if not key in self.resources:
            raise CortexError(HAS_NONE_ERROR, key, self.category)
        if self.resources[key] < qty:
            raise CortexError(HAS_ONLY_ERROR, key, self.resources[key], self.category)
        self.resources[key] -= qty
        if self.resources[key] < 0:
            del self.resources[key]
        return self.output(key)

    def output(self, name):
        key = clean_up_key(name)
        return '{0}: {1}'.format(key, self.resources[key])

    def output_all(self):
        output = ''
        prefix = ''
        for name in list(self.resources):
            output += prefix + self.output(name)
            prefix = '\n'
        return output

class GroupedNamedDice:
    def __init__(self):
        self.groups = {}

    def is_empty(self):
        return not self.groups

    def add(self, group, name, size):
        key = clean_up_key(group)
        if not key in self.groups:
            self.groups[key] = NamedDice()
        self.groups[key].add(name, size)
        return self.output(key)

    def step_up(self, group, name):
        key = clean_up_key(group)
        self.groups[key].step_up(name)
        return self.output(key)

    def step_down(self, group, name):
        key = clean_up_key(group)
        self.groups[key].step_down(name)
        return self.output(key)

    def get_all_names(self):
        return list(self.dice)

    def output(self, group):
        return group + ': ' + self.groups[group].output_all(separator=', ')

    def output_all(self):
        output = ''
        prefix = ''
        for group in list(self.groups):
            output += prefix + self.output(group)
            prefix = '\n'
        return output

class CortexGame:
    def __init__(self):
        self.pinned_message = None
        self.complications = NamedDice('complication')
        self.plot_points = Resources('plot points')
        self.pools = DicePools()
        self.stress = GroupedNamedDice()
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

class CortexPal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = []

    def get_game_info(self, context):
        game_info = None
        game_key = [context.guild.id, context.message.channel.id]
        for existing_game in self.games:
            if game_key == existing_game[0]:
                game_info = existing_game[1]
        if not game_info:
            game_info = CortexGame()
            self.games.append([game_key, game_info])
        return game_info

    @commands.command()
    async def info(self, ctx):
        game = self.get_game_info(ctx)
        await ctx.send(game.output())

    @commands.command()
    async def pin(self, ctx):
        pins = await ctx.channel.pins()
        for pin in pins:
            if pin.author == self.bot.user:
                await pin.unpin()
        game = self.get_game_info(ctx)
        game.pinned_message = await ctx.send(game.output())
        await game.pinned_message.pin()

    @commands.command()
    async def comp(self, ctx, *args):
        logging.info("comp command invoked")
        output = ''
        update_pin = False
        try:
            if not args:
                output = 'Use the `$comp` command like this:\n`$comp add 6 cloud of smoke` (creates a D6 Cloud Of Smoke complication)\n`$comp stepdown dazed` (steps down the Dazed complication)'
            else:
                game = self.get_game_info(ctx)
                separated = separate_dice_and_name(args[1:])
                dice = separated['dice']
                name = separated['name']
                if args[0] in ADD_SYNONYMS:
                    if not dice:
                        raise CortexError(DIE_MISSING_ERROR)
                    elif len(dice) > 1:
                        raise CortexError(DIE_EXCESS_ERROR)
                    elif dice[0].qty > 1:
                        raise CortexError(DIE_EXCESS_ERROR)
                    output = game.complications.add(name, dice[0])
                    update_pin = True
                elif args[0] == 'stepup':
                    output = game.complications.step_up(name)
                    update_pin = True
                elif args[0] == 'stepdown':
                    output = game.complications.step_down(name)
                    update_pin = True
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
        logging.info("pp command invoked")
        output = ''
        update_pin = False
        try:
            if not args:
                output = 'Use the `$pp` command like this:\n`$pp add Alice 3` (gives Alice 3 PP)\n`$pp remove Alice` (spends one of Alice\'s PP)'
            else:
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
        logging.info("roll command invoked")
        results = {}
        try:
            pool = DicePool()
            for arg in args:
                pool.add(Die(arg))
            await ctx.send(pool.roll())
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

    @commands.command()
    async def pool(self, ctx, *args):
        logging.info("pool command invoked")
        output = ''
        update_pin = False
        game = self.get_game_info(ctx)
        try:
            if not args:
                output = 'Use the `$pool` command like this:\n`$pool add Doom 6 8` (gives the Doom pool a D6 and D8)\n`$pool remove Doom 10` (spends a D10 from the Doom pool)'
            elif args[0] in ADD_SYNONYMS:
                for arg in args[2:]:
                    output = game.pools.add(args[1], int(arg))
                update_pin = True
            elif args[0] in REMOVE_SYNOYMS:
                for arg in args[2:]:
                    output = game.pools.remove(args[1], int(arg))
                update_pin = True
            elif args[0] == 'roll':
                output = game.pools.roll(args[1])
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
        logging.info("stress command invoked")
        output = ''
        update_pin = False
        try:
            if not args:
                output = 'use the `$stress` command like this:\n`$stress add Amy 8` (gives Amy D8 stress)\n`$stress add Ben Mental 6` (gives Ben D6 mental stress)\n`$stress stepup Cat Social` (steps up Cat\'s social stress)'
            else:
                game = self.get_game_info(ctx)
                if args[0] in ADD_SYNONYMS:
                    if args[2].isdecimal():
                        stress_name = UNTYPED_STRESS
                        die = int(args[2])
                    else:
                        stress_name = args[2]
                        die = int(args[3])
                    output = 'Stress for ' + game.stress.add(args[1], stress_name, die)
                    update_pin = True
                elif args[0] == 'stepup':
                    if len(args) == 2:
                        stress_name = UNTYPED_STRESS
                    else:
                        stress_name = args[2]
                    output = 'Stress for ' + game.stress.step_up(args[1], stress_name)
                    update_pin = True
                elif args[0] == 'stepdown':
                    if len(args) == 2:
                        stress_name = UNTYPED_STRESS
                    else:
                        stress_name = args[2]
                    output = 'Stress for ' + game.stress.step_down(args[1], stress_name)
                    update_pin = True
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
        logging.info("asset command invoked")
        output = ''
        update_pin = False
        try:
            game = self.get_game_info(ctx)
            if not args:
                output = 'This is where we give syntax help for the command'
            elif args[0] == 'new':
                find_die_error(args[1])
                name = ' '.join(args[2:])
                output = 'New asset: ' + game.assets.add(name, int(args[1]))
                update_pin = True
            elif args[0] == 'stepup':
                name = ' '.join(args[1:])
                output = 'Stepped up ' + game.assets.step_up(name)
                update_pin = True
            elif args[0] == 'stepdown':
                name = ' '.join(args[1:])
                output = 'Stepped down ' + game.assets.step_down(name)
                update_pin = True
            if update_pin and game.pinned_message:
                await game.pinned_message.edit(content=game.output())
            await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)
        except:
            logging.error(traceback.format_exc())
            await ctx.send(UNEXPECTED_ERROR)

logging.info("Bot startup")
bot.add_cog(CortexPal(bot))
bot.run(TOKEN)
