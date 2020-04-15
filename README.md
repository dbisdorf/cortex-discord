# cortex-discord
A Discord bot to assist Cortex Prime RPG players.

Note that this bot is still in early development. You may encounter bugs or gaps in functionality. Feel free to contact me with any bug reports, or, if you prefer, you can file them here.

## Inviting

As of April 2020, I have a public instance of this bot running 24/7. You can invite this bot to your Discord server by *(instructions to appear here when the bot is available).* The bot only requires permission to send and manage messages.

A few warnings about the public bot:

- I can't guarantee that it will be up 100% of the time. **Bugs or other issues may cause the bot to go down unexpectedly** and to stay down for an indeterminate duration.
- Because it's in early development, **the behavior of the bot may change often.** I might add or remove commands, or change the syntax of commands. Unfortunately, you probably won't know a change has occurred until you try something that worked yesterday and find that it doesn't work today.
- Even when it's running and I'm not touching it, **it might not work right.** Testing and usage will eventually help me eliminate bugs I haven't found yet, but I might not have quick solutions for those bugs.
- The bot doesn't store game information persistently. **All information goes away when I shut the bot down** for upgrades or maintenance. I'll try not to shut the bot down if someone is using it, so you'll probably be safe during a three or four hour session. But if you update a doom pool on Monday, and I restart the bot on Tuesday, that doom pool will be empty if you sign in on Wednesday. This means the bot will probably be safe for live interactive roleplaying sessions, but **not for long-term play-by-post games.** This may change in the future.

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

## Hosting

If you want to host an instance of this bot, start by setting up a new bot through the Discord developer's portal. Then install the CortexPal Python code wherever you like. When you execute it, the code will look for a cortexpal.ini file in the current working directory. The contents of this file should look like this:

```
[logging]
file=cortexpal.log

[discord]
token=abcdefghijklmnopqrstuvwxyz
```

In the [logging] section, the "file" attribute should hold the name of the log file you wish to use.

In the [discord] section, the "token" attribute must contain your secure Discord bot token. Take whatever steps are necessary on your host machine to keep this information secret.

When inviting the bot to a server, assign it the "bot" scope and the "Send Messages" and "Manage Messages" permissions.
