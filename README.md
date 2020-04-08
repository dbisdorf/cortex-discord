# cortex-discord
Discord bot to assist Cortex Prime RPG players.

Note that this bot is still in early development. You may encounter bugs or gaps in functionality. Feel free to contact me with any bug reports, or, if you prefer, you can file them here.

## Inviting

As of April 2020, I have a public instance of this bot running 24/7. You can invite this bot to your Discord server...

## Usage

When the bot is running, type "$help" to get a list of all commands, or type "$help (command)" to get help on a specific command.

## Hosting

If you want to host an instance of this bot, install the Python code wherever you like. When you execute it, the code will look for a cortexpal.ini file in the current working directory. The contents of this file should look like this:

```
[logging]
file=cortexpal.log

[discord]
token=abcdefghijklmnopqrstuvwxyz
```

In the [logging] section, the "file" attribute should hold the name of the log file you wish to use.

In the [discord] section, the "token" attribute will contain your secure Discord bot token.
