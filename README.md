# lastfm-red
LastFM Ported to Red

This is a port of MisoBot, with some functionality removed or added and made to use config. 

## changelog

- v1.1.0 - adds `[p]scrobble` and `[p]fm scrobbler` commands and improves error messages
- v1.1.1 - improves algorithm to detect if a song should be scrobbled
- v1.1.2 - fix `[p]whoknows` command bug
- v1.1.3 - add color to `[p]fm profile` embed
- v1.1.4 - use timestamps in `[p]fm profile` embed
- v1.1.5 - increase cooldown in `[p]fm scrobble` command
- v1.2.0 - add `[p]fm love`,`[p]fm unlove` and `[p]fm loved` + add a heart to the title in `[p]fm np` if the song is loved
- v1.2.1 - add page number to `[p]fm loved` embed
- v1.3.0 - add `[p]fm streak` command
- v1.4.0 - update login message, make `[p]fm login` much faster, adds `[p]fm tag` with a bunch of subcommands
- v1.4.1 - fix fm login error message
- v1.4.2 - clean up code for needing to log in