# Harmonic Playlist Optimizer

This tool optimizes the order of an M3U playlist based on harmonic mixing rules (Camelot Wheel compatibility) and tempo. Unlike simple sorting, it uses Simulated Annealing to optimize the flow of the entire playlist.

## Requirements

1. **Python 3.x** (the `python` command, or the `py` launcher, must be available on your PATH).
2. The **`mutagen`** library for reading tags: `pip install mutagen`

## Tagging Requirements

BPM and Camelot key are read from the audio file tags. MP3 (ID3), FLAC/OGG/Opus (Vorbis comments) and M4A are supported.

| Data              | Tag Location                                              | Format/Rule                                       |
| ----------------- | --------------------------------------------------------- | ------------------------------------------------- |
| **BPM** (Tempo)   | `TBPM` or `TXXX:BPM` (MP3), `bpm` (Vorbis), `tmpo` (M4A)  | A number, decimals are allowed (e.g. `128` or `127.9`). |
| **Key** (Camelot) | `COMM` (Comment), `TKEY`, `TXXX:KEY` (MP3), `initialkey`/`comment` (Vorbis) | Must be the first word (e.g. `8A`, `8A - Energy 6`). |

Tracks without usable tags are **not optimized**, see below.

## Usage

1. Export the playlist from Mixxx (right-click the playlist, export as M3U).
2. Double-click **`_sort.bat`** and enter the path, **or drag & drop** the exported file onto `_sort.bat`.
3. Import the sorted playlist (`MyPartyMix_sorted.m3u`) back into Mixxx.

`playlist-sorter.py` is expected **next to `_sort.bat`**. Without the batch file:

```powershell
python playlist-sorter.py "MyPartyMix.m3u" "MyPartyMix_sorted.m3u" --unsorted separate
```

### Tracks that cannot be optimized

Tracks with missing or unusable tags (and missing or unreadable files) are never silently dropped. Choose what happens with them (`UNSORTED_MODE` in `_sort.bat`, or `--unsorted`):

| Mode | Result |
| --- | --- |
| `separate` (default) | A second playlist `MyPartyMix_unsorted.m3u` with these tracks in their original order. |
| `append` | They are appended to the end of the sorted playlist. |
| `omit` | They are left out. |

In every mode the console lists each affected track with the reason.

### Options

| Option | Description |
| --- | --- |
| `--unsorted separate\|append\|omit` | See above. |
| `--first TEXT` / `--last TEXT` | Pin the track whose path contains `TEXT` to the start / end (e.g. the opener and the closer of a set). |
| `--trend up\|down` | Prefer rising or falling tempo (a small bonus, key harmony stays more important). |
| `--restarts N` | Independent optimization runs, the best one wins (default 4). |
| `--iterations N` | Steps per run (default: depends on the playlist size). |
| `--seed N` | Fixed random seed for reproducible results. |
| `--no-comments` | Do not write the key/tempo comment lines (see Output). |

`_sort.bat` passes additional arguments from its `EXTRA_ARGS` line.

### Output

The optimized playlist is created in the same directory as the input, using the suffix `_sorted`. The file encoding (UTF-8 or Windows-1252/Latin-1) is detected and kept, so paths with umlauts stay intact. `#EXTINF` lines are preserved, relative paths are adjusted if the output is written to another directory. At the end the tool lists the **weak transitions** (incompatible keys or large tempo gaps) of the result.

**Comment lines:** Every track gets a comment line above it with its position, Camelot key and BPM. Weak transitions are marked, tracks that were not optimized carry the reason:

```
# 12 | 8A | 120 BPM
../music/Track_12.mp3
# 13 | 9B | 95.4 BPM | WEAK transition from previous: key 8A -> 9B, tempo gap 26.0% (120 -> 95.4 BPM)
../music/Track_13.mp3
```

Mixxx skips lines starting with `#` when importing, so the comments are harmless there. They are only visible in a text editor (Mixxx does not display them). Use `--no-comments` to switch them off.

## Optimization Logic

1. **Scoring:** Every possible transition between two tracks gets a score once (a matrix).
2. **Initialization:** The order is shuffled randomly (pinned tracks stay in place).
3. **Moves:** Each step swaps two tracks, moves one track, or reverses a segment. Only the changed transitions are re-evaluated, so a step is very cheap.
4. **Acceptance:** Better orders are kept. Worse ones are accepted with a probability that shrinks with the "temperature", which avoids dead ends.
5. **Restarts:** Several independent runs, the best result is kept.

### Scoring Criteria

| Rule                 | Description                                                                             | Default |
| -------------------- | --------------------------------------------------------------------------------------- | ------- |
| **Key Harmony**      | Same key, +/- 1 hour on the wheel, or relative major/minor (A and B at the same number). | +1000 match, -500 clash |
| **Tempo Proximity**  | **Relative** tempo gap in percent, symmetric. Half/double time counts as a match (70 vs 140 BPM = 0 %). | +100 up to 4 %, +50 up to 8 %, -10 above |
| **Tempo Limit**      | A gap above 30 % gets a massive penalty.                                                | -2000 |

The 8 % window matches the sync window of the `midiAutoDJ` script, so sorted transitions can be beatmatched there. All values are constants at the top of `playlist-sorter.py`.

## Performance Tuning

Edit the "Simulated Annealing Settings" at the top of `playlist-sorter.py`, or use the command line options:

- **SA_ITERATIONS_PER_TRACK / SA_MIN_ITERATIONS**: Steps per run and track. The temperature is tied to the step count, so every run cools completely, whatever you choose.
- **SA_RESTARTS**: More restarts give more reliable results for long playlists.
