# TO DO
# Validate all die faces and give error if needed
# Master help command, and help for individual commands
# Reduce repetition in command methods
# Constants for all static messages
# Match verbs against synonym arrays.
# Document synonyms in user help.
# Is there any point in using subcommands?
# A straight array of CortexGames might not be the most efficient for sorting purposes
# Auto-capitalizing for names of pools/stress/complications/assets/etc?
# Maybe the Cortex Game Information header is superfluous
# Hero dice are a pool. Gonna need GroupedDicePools then.
# Also do crisis and "growth" pools. Make "pool" a generic concept?
# Comments!
# I suppose the different error messages should map to different exceptions.
# Fix plurals in error messages.

import discord
import random
import os
from discord.ext import commands

PREFIX = '$'
UNTYPED_STRESS = 'General'
DIE_FACE_ERROR = '{0} is not a valid die size. You may only use dice with sizes of 4, 6, 8, 10, or 12.'
NOT_EXIST_ERROR = 'That {0} doesn\'t exist yet.'
HAS_NONE_ERROR = '{0} doesn\'t have any {1}.'
HAS_ONLY_ERROR = '{0} only has {1} {2}.'

TOKEN = os.getenv('CORTEX_DISCORD_TOKEN')
bot = commands.Bot(command_prefix='$')

class CortexError(Exception):
    def __init__(self, message, *args):
        self.message = message
        self.args = args

    def __str__(self):
        return self.message.format(*(self.args))

def get_matching_key(typed_key, stored_keys):
    match = None
    normal_typed_key = typed_key.replace(' ', '').lower()
    for stored_key in stored_keys:
        normal_stored_key = stored_key.replace(' ', '').lower()
        if normal_stored_key.startswith(normal_typed_key):
            match = stored_key
    return match

def find_die_error(die):
    error = None
    if not die in ['4', '6', '8', '10', '12']:
        raise CortexError(DIE_FACE_ERROR, die)

class NamedDice:
    def __init__(self, category):
        self.dice = {}
        self.category = category

    def is_empty(self):
        return not self.dice

    def add(self, name, size):
        key = get_matching_key(name, list(self.dice))
        if not key:
            self.dice[name] = size
            key = name
        elif self.dice[key] < size:
            self.dice[key] = size
        else:
            self.dice[key] += 2
        return self.output(key)

    def step_up(self, name):
        key = get_matching_key(name, list(self.dice))
        if key:
            self.dice[key] += 2
        else:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        return self.output(key)

    def step_back(self, name):
        key = get_matching_key(name, list(self.dice))
        if key:
            self.dice[key] -= 2
            if self.dice[key] < 4:
                del self.dice[key]
        else:
            raise CortexError(NOT_EXIST_ERROR, self.category)
        return self.output(key)

    def get_all_names(self):
        return list(self.dice)

    def output(self, name):
        return 'D{0} {1}'.format(self.dice[name], name)

    def output_all(self, separator='\n'):
        output = ''
        prefix = ''
        for name in list(self.dice):
            output += prefix + self.output(name)
            prefix = separator
        return output

class DicePool:
    def __init__(self):
        self.dice = {}

    def is_empty(self):
        return not self.dice

    def add(self, size, qty=1):
        if size in self.dice:
            self.dice[size] += qty
        else:
            self.dice[size] = qty
        return self.output()

    def remove(self, size, qty=1):
        self.dice[size] -= qty
        if self.dice[size] <= 0:
            del self.dice[size]
        return self.output()

    def output(self):
        if self.is_empty():
            return 'empty'
        output = ''
        sorted_sizes = sorted(list(self.dice))
        for size in sorted_sizes:
            if self.dice[size] == 1:
                output += 'D{0} '.format(size)
            else:
                output += '{0}D{1} '.format(self.dice[size], size)
        return output

class DicePools:
    def __init__(self):
        self.pools = {}

    def is_empty(self):
        return not self.pools

    def add(self, name, size, qty=1):
        key = get_matching_key(name, list(self.pools))
        if not key:
            self.pools[name] = DicePool()
            key = name
        output = self.pools[key].add(size, qty)
        return '{0}: {1}'.format(key, output)

    def remove(self, name, size, qty=1):
        key = get_matching_key(name, list(self.pools))
        output = self.pools[key].remove(size, qty)
        return '{0}: {1}'.format(key, output)

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
        key = get_matching_key(name, list(self.resources))
        if not key:
            self.resources[name] = qty
            key = name
        else:
            self.resources[key] += qty
        return self.output(key)

    def remove(self, name, qty=1):
        key = get_matching_key(name, list(self.resources))
        if not key:
            raise CortexError(HAS_NONE_ERROR, name, self.category)
        if self.resources[key] < qty:
            raise CortexError(HAS_ONLY_ERROR, key, self.resources[key], self.category)
        self.resources[key] -= qty
        if self.resources[key] < 0:
            del self.resources[key]
        return self.output(key)

    def output(self, name):
        key = get_matching_key(name, list(self.resources))
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
        key = get_matching_key(group, list(self.groups))
        if not key:
            self.groups[group] = NamedDice()
            key = group
        self.groups[key].add(name, size)
        return self.output(key)

    def step_up(self, group, name):
        key = get_matching_key(group, list(self.groups))
        self.groups[key].step_up(name)
        return self.output(key)

    def step_back(self, group, name):
        key = get_matching_key(group, list(self.groups))
        self.groups[key].step_back(name)
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
        game = self.get_game_info(ctx)
        output = ''
        update_pin = False
        try:
            if not args:
                output = 'Use the `$comp` command like this:\n`$comp new 6 Cloud of Smoke` (creates a D6 Cloud of Smoke complication)\n`$comp stepback Dazed` (steps back the Dazed complication)'
            elif args[0] == 'new':
                find_die_error(args[1])
                name = ' '.join(args[2:])
                output = 'New complication: ' + game.complications.add(name, int(args[1]))
                update_pin = True
            elif args[0] == 'stepup':
                name = ' '.join(args[1:])
                output = 'Stepped up: ' + game.complications.step_up(name)
                update_pin = True
            elif args[0] == 'stepback':
                name = ' '.join(args[1:])
                output = 'Stepped back: ' + game.complications.step_back(name)
                update_pin = True
            if update_pin and game.pinned_message:
                await game.pinned_message.edit(content=game.output())
            await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)

    @commands.command()
    async def pp(self, ctx, *args):
        output = ''
        update_pin = False
        try:
            if not args:
                output = 'Use the `$pp` command like this:\n`$pp give Alice 3` (gives Alice 3 PP)\n`$pp spend Alice` (spends one of Alice\'s PP)'
            else:
                game = self.get_game_info(ctx)
                if len(args) > 2:
                    qty = int(args[2])
                else:
                    qty = 1
                if args[0] == 'give':
                    output = 'Plot points for ' + game.plot_points.add(args[1], qty)
                    update_pin = True
                elif args[0] == 'spend':
                    output = 'Plot points for ' + game.plot_points.remove(args[1], qty)
                    update_pin = True
            if update_pin and game.pinned_message:
                await game.pinned_message.edit(content=game.output())
            await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)

    @commands.command()
    async def roll(self, ctx, *args):
        results = {}
        try:
            for arg in args:
                find_die_error(arg)
                if error:
                    break
                die = int(arg)
                roll = str(random.SystemRandom().randrange(1, int(die) + 1))
                if roll == '1':
                    roll = '**(1)**'
                if die in results:
                    results[die].append(roll)
                else:
                    results[die] = [roll]
            output = ''
            sorted_keys = sorted(list(results))
            for key in sorted_keys:
                output += 'D{0} : {1}\n'.format(key, ', '.join(results[key]))
            await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)

    @commands.command()
    async def pool(self, ctx, *args):
        output = ''
        update_pin = False
        game = self.get_game_info(ctx)
        try:
            if not args:
                output = 'Use the `$pool` command like this:\n`$pool give Doom 6 8` (gives the Doom pool a D6 and D8)\n`$pool spend Doom 10` (spends a D10 from the Doom pool)'
            elif args[0] == 'give':
                for arg in args[2:]:
                    output = game.pools.add(args[1], int(arg))
                update_pin = True
            elif args[0] == 'spend':
                for arg in args[2:]:
                    output = game.pools.remove(args[1], int(arg))
                update_pin = True
            if update_pin and game.pinned_message:
                await game.pinned_message.edit(content=game.output())
            await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)

    @commands.command()
    async def stress(self, ctx, *args):
        output = ''
        update_pin = False
        try:
            if not args:
                output = 'use the `$stress` command like this:\n`$stress give Amy 8` (gives Amy D8 stress)\n`$stress give Ben Mental 6` (gives Ben D6 mental stress)\n`$stress stepup Cat Social` (steps up Cat\'s social stress)'
            else:
                game = self.get_game_info(ctx)
                if args[0] == 'give':
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
                elif args[0] == 'stepback':
                    if len(args) == 2:
                        stress_name = UNTYPED_STRESS
                    else:
                        stress_name = args[2]
                    output = 'Stress for ' + game.stress.step_back(args[1], stress_name)
                    update_pin = True
            if update_pin and game.pinned_message:
                await game.pinned_message.edit(content=game.output())
            await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)

    @commands.command()
    async def asset(self, ctx, *args):
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
            elif args[0] == 'stepback':
                name = ' '.join(args[1:])
                output = 'Stepped back ' + game.assets.step_back(name)
                update_pin = True
            if update_pin and game.pinned_message:
                await game.pinned_message.edit(content=game.output())
            await ctx.send(output)
        except CortexError as err:
            await ctx.send(err)

bot.add_cog(CortexPal(bot))
bot.run(TOKEN)
