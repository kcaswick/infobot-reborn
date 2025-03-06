# Infobot Legacy Features Documentation

## Overview
This document catalogs the core features and behaviors of the original Infobot based on examination of legacy files. The information here is derived from the following sources:

- `/Egor-try1/doc/infobot_guide.html` - Official guide for Infobot version 0.44.3
- `/Egor-try1/doc/intro.bit` - Brief introduction to Infobot features
- `/Egor-try1/Egor.log` - Log of Infobot interactions (Egor instance)
- `/Egor-try1/Egor-is.txt` and `/Egor-try1/Egor-are.txt` - Factoid databases

## Core Knowledge Base Features

### Factoid Storage and Retrieval
- **Setting Factoids**: `X is Y` - Stores a factoid where X is the key and Y is the value
- **Accessing Factoids**: `What is X?`, `Where is X?`, or just `X?` - Retrieves stored factoids
- **Response Format**: Typically responds with "X is Y" for a factoid query

### Special Response Formatting
- **`<reply>` Tag**: `X is <reply> Y` - Makes the bot respond with just "Y" instead of "X is Y"
- **`<action>` Tag**: `X is <action> Y` - Makes the bot respond with an action (similar to IRC /me)
- **Random Responses**: `X is A|B|C|D` - Bot will randomly choose one of the pipe-separated values
- **Variable Substitution**:
  - `$who` - Contains the nickname of the person addressing the bot
  - `$date` - Contains the current date and time at the bot's host

### Factoid Modification
- **Appending**: `X is also Y` - Extends an existing factoid
- **Erasing**: `forget X` - Deletes a factoid
- **Replacing**: `no, X is Y` - Replaces the prior definition completely
- **Altering Parts**: `X =~ s/A/B/` - Changes part of a factoid using regex substitution
- **Backwacking**: Using `\` to protect items from evaluation (e.g., `X \is Y` to prevent "is" from being interpreted as a command)

## Conversational Style

From the log file and factoid databases, we can observe:

- **Natural Language Processing**: The bot understands various ways to ask for information
- **Casual, Often Witty Responses**: The factoid database shows many humorous or informal responses
- **Addressing Style**: Responds differently when directly addressed versus overhearing conversations
- **Relay Mechanism**: `tell someone about X` - Can relay information to other users

### Example Interaction Patterns
From the log, we can see typical interactions:

```
[User] What is love?
[Egor] Isn't that a bit silly, [User]?

[User] tell me about ice cream
[Egor] ice cream is way too cold for wearing, mojo ;)

[User] tell m about life
[Egor] told m about life (keyboard wants you to know: life is a series of meetings and partings... or that sludge that looks up and talks to you sometimes)
```

## Additional Features

### Social Features
- **Karma Tracking**: `X++` and `X--` - Increments or decrements karma for a concept
- **Status Reporting**: `status` - Reports uptime, number of factoids, modifications, and questions

### Utility Features
- **Weather**: `weather KAGC` or `metar KAGC` - Gets weather information from NOAA stations
- **Search Interfaces**:
  - `imdb for title` - Looks up movies in the Internet Movie Database
  - `webster for word` - Searches Webster's 1913 dictionary
  - `foldoc for term` - Searches the Free On-Line Dictionary of Computing
  - `search google for query` - Performs a web search (with support for multiple engines)
- **Currency Conversion**: `change 100 USD to DEM` - Converts between currencies
- **RSS Support**: `<rss="http://site.com/feed.rss">` - Fetches and displays RSS feeds

### Administrative Functions
- **Channel Management** (IRC-specific):
  - `join #channel` - Joins a channel
  - `part #channel` or `leave #channel` - Leaves a channel
- **User Management**:
  - `ignore nickname` or `ignore *.domain.com` - Ignores users by nickname or hostmask
  - `op` - Gives operator status to authorized users
  - `die` - Shuts down the bot (owner only)

### Data Management
- The original Infobot used DBM files to store factoids
- Provided utilities:
  - `update_db` - Imports factoids from text files to DBM
  - `dump_db` - Exports factoids from DBM to text files

## Factoid Database Analysis

The factoid database files reveal that Infobot stored two types of factoids:
- "is" factoids - Statements about what something is
- "are" factoids - Statements about what things are (plural)

Example entries from Egor-is.txt:
```
[redacted]'s pic => still on her site
reality => merely a concept
hair => always optional
```

Example entries from Egor-are.txt:
```
wolf spiders => early this year...
frozen waffles => awesome
crabs in ga => alot smaller i use drop baskets for them as well
```

The database shows that factoids covered a wide range of topics, from philosophical statements to practical information and humor.

## Additional Add-ons Worth Preserving
- **Language Translation**: Originally provided via Babelfish integration
- **Nickometer**: Measures how "lame" a nickname is (percentage-based)
- **Slashdot Headlines**: Retrieves news from technology sites
- **Flight Information**: Original implementation had US Airways flight data
- **Excuse Server**: Generates humorous excuses