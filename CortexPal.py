import discord
import random
import os
import traceback
import re
import logging
import configparser
import datetime
from discord.ext import commands
from datetime import datetime

PREFIX = '$'

UNTYPED_STRESS = 'General'

ADD_SYNONYMS = ['add', 'give', 'new']
REMOVE_SYNOYMS = ['remove', 'spend', 'delete', 'subtract']
UP_SYNONYMS = ['stepup', 'up']
DOWN_SYNONYMS = ['stepdown', 'down']

DICE_EXPRESSION = re.compile('(\d*(d|D))?(4|6|8|10|12)')
DIE_SIZES = [4, 6, 8, 10, 12]

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
            return 'Raised: ' + self.output(name)

    def remove(self, name):
        if not name in self.dice:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        output = 'Removed: ' + self.output(name)
        del self.dice[name]
        return output

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

"""
DicePool: a single-purpose collection of die sizes and quantities.
Suitable for doom pools, crisis pools, and growth pools.
"""
class DicePool:
    def __init__(self, roller, incoming_dice=[]):
        self.roller = roller
        self.dice = [None, None, None, None, None]
        self.add(incoming_dice)

    def is_empty(self):
        return not self.dice

    def add(self, dice):
        for die in dice:
            index = DIE_SIZES.index(die.size)
            if self.dice[index]:
                self.dice[index].qty += die.qty
            else:
                self.dice[index] = die
        return self.output()

    def remove(self, dice):
        for die in dice:
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
    def __init__(self, roller):
        self.roller = roller
        self.pools = {}

    def is_empty(self):
        return not self.pools

    def add(self, name, dice):
        if not name in self.pools:
            self.pools[name] = DicePool(self.roller)
        self.pools[name].add(dice)
        return '{0}: {1}'.format(name, self.pools[name].output())

    def remove(self, name, dice):
        if not name in self.pools:
            raise CortexError(NOT_EXIST_ERROR, 'pool')
        self.pools[name].remove(dice)
        return '{0}: {1}'.format(name, self.pools[name].output())

    def roll(self, name):
        return self.pools[name].roll()

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
        if not name in self.resources:
            self.resources[name] = qty
        else:
            self.resources[name] += qty
        return self.output(name)

    def remove(self, name, qty=1):
        if not name in self.resources:
            raise CortexError(HAS_NONE_ERROR, name, self.category)
        if self.resources[name] < qty:
            raise CortexError(HAS_ONLY_ERROR, name, self.resources[name], self.category)
        self.resources[name] -= qty
        return self.output(name)

    def output(self, name):
        return '{0}: {1}'.format(name, self.resources[name])

    def output_all(self):
        output = ''
        prefix = ''
        for name in list(self.resources):
            output += prefix + self.output(name)
            prefix = '\n'
        return output

class GroupedNamedDice:
    def __init__(self, category):
        self.groups = {}
        self.category = category

    def is_empty(self):
        return not self.groups

    def add(self, group, name, die):
        if not group in self.groups:
            self.groups[group] = NamedDice(self.category)
        self.groups[group].add(name, die)
        return self.output(group)

    def remove(self, group, name):
        if not group in self.groups:
            raise CortexError(HAS_NONE_ERROR, group, self.category)
        self.groups[group].remove(name)
        return self.output(group)

    def step_up(self, group, name):
        self.groups[group].step_up(name)
        return self.output(group)

    def step_down(self, group, name):
        self.groups[group].step_down(name)
        return self.output(group)

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
    def __init__(self, roller):
        self.roller = roller
        self.pinned_message = None
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
                    frequency += ' : **{0}** {1},{2}%'.format(
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
            game_info = CortexGame(self.roller)
            self.games.append([game_key, game_info])
        return game_info

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
                    output = 'Stress for ' + game.stress.add(owner_name, stress_name, dice[0])
                    update_pin = True
                elif args[0] in REMOVE_SYNOYMS:
                    output = 'Stress for ' + game.stress.remove(owner_name, stress_name)
                    update_pin = True
                elif args[0] in UP_SYNONYMS:
                    output = 'Stress for ' + game.stress.step_up(owner_name, stress_name)
                    update_pin = True
                elif args[0] in DOWN_SYNONYMS:
                    output = 'Stress for ' + game.stress.step_down(owner_name, stress_name)
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
    async def report(self, ctx):
        """
        Report the bot's statistics.
        """

        output = (
        '**CortexPal Usage Report**\n'
        'Bot started up at UTC {0}.\n'
        'Last user command was at UTC {1}.\n'
        '\n'
        ).format(self.startup_time, self.last_command_time)

        output += self.roller.output()
        await ctx.send(output)

logging.info("Bot startup")
bot.add_cog(CortexPal(bot))
bot.run(TOKEN)
