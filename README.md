# cortex-discord
A Discord bot to assist Cortex Prime RPG players.

This bot uses the discord.py library (https://pypi.org/project/discord.py/).

Feel free to contact me with any bug reports, or, if you prefer, you can file them here.

**Warning:** Because of new Discord restrictions (https://support-dev.discord.com/hc/en-us/articles/4404772028055-Message-Content-Access-Deprecation-for-Verified-Bots), the tech used in this bot won't work after April 2022. Consider using CortexPal2000 instead (https://github.com/dbisdorf/cortex-discord-2).

## Inviting

As of April 2020, I have a public instance of this bot running 24/7. You can invite this bot to your Discord server by browsing to this URL: https://discordapp.com/api/oauth2/authorize?client_id=694239819454480445&permissions=10240&scope=bot

The bot only requires permission to send and manage messages. It's been reasonably stable so far, but I can't guarantee that it will be up 100% of the time. Bugs or other issues may cause the bot to go down unexpectedly and to stay down for an indeterminate duration.

## Usage

The bot pays attention to commands beginning with a dollar sign ($). When the bot is running, type "$help" to get a list of all commands, or type "$help (command)" to get help on a specific command. You can also type the name of a command by itself (like "$pp" or "$asset") to get help for that command.

The bot expects that a game is limited to one channel on one server. When you create complications or assets or pools or whatever in one channel, you won't see them in another channel.

You can give dice to a command in one of two ways:

- Just give the size of the die. You could type "6" if you want a D6, or "10 10 10" if you want 3D10.
- Use standard "D" notation, like "D6" or "1D8" or "3D10".

You can give dice to a command either before or after the thing you're attaching the dice to. For instance, if you were creating a D6 On Fire complication, these two commands would be equivalent:

- $comp add 6 on fire
- $comp add on fire 6

The bot will also automatically capitalize the names of things for you. The two commands above would both produce a complication named "On Fire."

## Synonyms

The bot recognizes synonyms for some instructions, which you may find more succinct or intuitive.

- Instead of **add**, you may use **give**, **new**, or **create**.
- Instead of **remove**, you may use **spend**, **delete**, or **subtract'**.
- Instead of **stepup**, you may use **up**.
- Instead of **stepdown**, you may use **down**.

## Abandoned Games

The bot will delete game information that no one has updated in 180 days. This purge occurs on a channel-by-channel basis. In other words, if you are running a game in a channel on your server, and you don't execute any game commands in that channel for 180 days, the bot will delete all game information from that channel.

## Hosting

If you want to host an instance of this bot, start by setting up a new bot through the Discord developer's portal. Then install the CortexPal Python code wherever you like. When you execute it, the code will look for a cortexpal.ini file in the current working directory. The contents of this file should look like this:

```
[logging]
file=cortexpal.log

[discord]
token=abcdefghijklmnopqrstuvwxyz

[database]
file=cortexpal.db
```

In the [logging] section, the "file" attribute should hold the name of the log file you wish to use.

In the [discord] section, the "token" attribute must contain your secure Discord bot token. Take whatever steps are necessary on your host machine to keep this information secret.

In the [database] section, the "database" attribute should hold the name of the database file you wish to use. CortexPal uses sqlite3 as its database engine, which means all of its data will be in this single file, and you don't need to run or install a separate database server.

When inviting the bot to a server, assign it the "bot" scope and the "Send Messages" and "Manage Messages" permissions.

## Donate

If CortexPal is useful for you, and you feel like buying me a cup of tea, you can reach me through PayPal:

https://paypal.me/DonaldBisdorf
