# TO DO
# All info & settings should be specific to a server and channel
# Validate all die faces and give error if needed
# Give error when mandatory key does not appear (like decrementing PP for non-existent character)
# Master help command, and help for individual commands
# Pile?
# Reduce repetition in command methods
# Use list() instead of .keys() for dictionaries?
# Constants for static messages?
# "Giving" stress twice should add it together per game rules.
# Match verbs against synonym arrays.
# Document synonyms in user help.
# Move to an exception model of throwing errors.

import discord
import random
from discord.ext import commands

bot = commands.Bot(command_prefix='$')

TOKEN = 'Apparently a Discord token is private information, so I need to pull this info from an environment file instead.'
PREFIX = '$'
UNTYPED_STRESS = 'General'
DIE_FACE_ERROR = '{0} is not a valid die size. You may only use dice with sizes of 4, 6, 8, 10, or 12.'

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
        error = DIE_FACE_ERROR.format(die)
    return error

class CortexPal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.comp_pile = {}
        self.pp_pile = {}
        self.doom_pool = {}
        self.stress_pile = {}
        self.pinned_message = None

    def format_comp(self, key):
        return 'D{0} {1}'.format(self.comp_pile[key], key)

    def format_pp(self, key):
        return '{0}: {1}'.format(key, self.pp_pile[key])

    def format_stress(self, key):
        output = '{0}: '.format(key)
        stresses = self.stress_pile[key]
        if not stresses:
            output += 'none'
        elif len(stresses) == 1 and list(stresses)[0] == UNTYPED_STRESS:
            output += 'D{0}'.format(stresses[UNTYPED_STRESS])
        else:
            separator = ''
            for stress in stresses:
                output += '{0}{1} D{2}'.format(separator, stress, stresses[stress])
                separator = ', '
        return output

    def format_doom(self):
        output = ''
        dice = sorted(list(doom_pool.keys()))
        for die in dice:
            if self.doom_pool[die] == 1:
                output += 'D{0} '.format(die)
            else:
                output += '{0}D{1} '.format(self.doom_pool[die], die)
        return output

    def format_summary(self):
        content = '**Cortex Game Information**\n'
        if self.comp_pile:
            content += '\n**Complications**\n'
            for key in self.comp_pile:
                content += self.format_comp(key) + '\n'
        if self.pp_pile:
            content += '\n**Plot Points**\n'
            for key in self.pp_pile:
                content += self.format_pp(key) + '\n'
        if self.doom_pool:
            content += '\n**Doom Pool**\n' + self.format_doom()
        if self.stress_pile:
            content += '\n**Stress**\n'
            for key in self.stress_pile:
                content += self.format_stress(key) + '\n'
        return content

    """
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user != bot.user:
            if reaction.emoji == '⬆️':
                self.comp += 2
                await reaction.message.remove_reaction('⬆️', user)
            elif reaction.emoji == '⬇️':
                self.comp -= 2
                await reaction.message.remove_reaction('⬇️', user)
            await reaction.message.edit(content=self.format_comps())
    """

    @commands.command()
    async def info(self, ctx):
        await ctx.send(self.format_summary())

    @commands.command()
    async def pin(self, ctx):
        pins = await ctx.channel.pins()
        for pin in pins:
            if pin.author == self.bot.user:
                await pin.unpin()
        self.pinned_message = await ctx.send(self.format_summary())
        await self.pinned_message.pin()

    @commands.command()
    async def comp(self, ctx, *args):
        if not args:
            await ctx.send('This is where we give syntax help for the command')
        elif args[0] == 'new':
            new_key = ' '.join(args[2:])
            self.comp_pile[new_key] = int(args[1])
            await self.pinned_message.edit(content=self.format_summary())
            await ctx.send('New complication: ' + self.format_comp(new_key))
        elif args[0] == 'stepup':
            key = get_matching_key(args[1], self.comp_pile.keys())
            self.comp_pile[key] += 2
            await self.pinned_message.edit(content=self.format_summary())
            await ctx.send('Stepped up: ' + self.format_comp(key))
        elif args[0] == 'stepback':
            key = get_matching_key(args[1], self.comp_pile.keys())
            self.comp_pile[key] -= 2
            await self.pinned_message.edit(content=self.format_summary())
            await ctx.send('Stepped back: ' + self.format_comp(key))
        """
        sent = await ctx.send('D{0}: Complication'.format(self.comp))
        await sent.add_reaction('⬆️')
        await sent.add_reaction('⬇️')
        """

    @commands.command()
    async def pp(self, ctx, *args):
        if not args:
            await ctx.send('Use the `$pp` command like this:\n`$pp give Alice 3` (gives Alice 3 PP)\n`$pp spend Alice` (spends one of Alice\'s PP)')
        else:
            if len(args) > 2:
                qty = int(args[2])
            else:
                qty = 1
            if args[0] == 'give':
                key = get_matching_key(args[1], self.pp_pile.keys())
                if key:
                    self.pp_pile[key] += qty
                else:
                    key = args[1]
                    self.pp_pile[args[1]] = qty
                await self.pinned_message.edit(content=self.format_summary())
                await ctx.send('{0} now has {1} PP'.format(key, self.pp_pile[key]))
            elif args[0] == 'spend':
                key = get_matching_key(args[1], self.pp_pile.keys())
                if key:
                    self.pp_pile[key] -= qty
                    await self.pinned_message.edit(content=self.format_summary())
                    await ctx.send('{0} now has {1} PP'.format(key, self.pp_pile[key]))

    @commands.command()
    async def roll(self, ctx, *args):
        error = None
        results = {}
        for arg in args:
            error = find_die_error(arg)
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
        if error:
            await ctx.send(error)
        else:
            output = ''
            sorted_keys = sorted(results.keys())
            for key in sorted_keys:
                output += 'D{0} : {1}\n'.format(key, ', '.join(results[key]))
            await ctx.send(output)

    @commands.command()
    async def doom(self, ctx, *args):
        if not args:
            await ctx.send('Use the `$doom` command like this:\n`$doom give 6 8` (gives the doom pool a D6 and D8)\n`$doom spend 10` (spends a D10 from the doom pool)')
        else:
            if args[0] == 'give':
                for arg in args[1:]:
                    die = int(arg)
                    if die in self.doom_pool:
                        self.doom_pool[die] += 1
                    else:
                        self.doom_pool[die] = 1
                await self.pinned_message.edit(content=self.format_summary())
                await ctx.send('New doom pool: ' + self.format_doom())
            elif args[0] == 'spend':
                for arg in args[1:]:
                    die = int(arg)
                    if die in self.doom_pool:
                        self.doom_pool[die] -= 1
                        if self.doom_pool[die] == 0:
                            del self.doom_pool[die]
                await self.pinned_message.edit(content=self.format_summary())
                new_pool = self.format_doom()
                if not new_pool:
                    new_pool = 'empty'
                await ctx.send('New doom pool: ' + new_pool)

    @commands.command()
    async def stress(self, ctx, *args):
        if not args:
            await ctx.send('use the `$stress` command like this:\n`$stress give Amy 8` (gives Amy D8 stress)\n`$stress give Ben Mental 6` (gives Ben D6 mental stress)\n`$stress stepup Cat Social` (steps up Cat\'s social stress)')
        else:
            key = get_matching_key(args[1], self.stress_pile.keys())
            if not key:
                key = args[1]
                stresses = {}
                self.stress_pile[key] = stresses
            else:
                stresses = self.stress_pile[key]
            if args[0] == 'give':
                if args[2].isdecimal():
                    stress_name = UNTYPED_STRESS
                    die = int(args[2])
                else:
                    stress_name = get_matching_key(args[2], list(stresses))
                    if not stress_name:
                        stress_name = args[2]
                    die = int(args[3])
                stresses[stress_name] = die
                await self.pinned_message.edit(content=self.format_summary())
                await ctx.send('Stress for ' + self.format_stress(key))
            elif args[0] == 'stepup':
                if len(args) == 2:
                    stress_name = UNTYPED_STRESS
                else:
                    stress_name = get_matching_key(args[2], list(stresses))
                stresses[stress_name] += 2
                await self.pinned_message.edit(content=self.format_summary())
                await ctx.send('Stress for ' + self.format_stress(key))
            elif args[0] == 'stepdown':
                if len(args) == 2:
                    stress_name = UNTYPED_STRESS
                else:
                    stress_name = get_matching_key(args[2], list(stresses))
                stresses[stress_name] -= 2
                await self.pinned_message.edit(content=self.format_summary())
                await ctx.send('Stress for ' + self.format_stress(key))

bot.add_cog(CortexPal(bot))
bot.run(TOKEN)
