#!/usr/bin/env python3
"""
Harmonic Playlist Optimizer

Reorders an M3U playlist by Camelot Wheel compatibility and tempo, using Simulated Annealing.
Tracks that cannot be optimized (missing tags, unreadable files) are written to a second
playlist, appended to the sorted one, or omitted (see --unsorted).

Usage:
    python playlist-sorter.py <input.m3u> [output.m3u] [options]
"""
import argparse
import codecs
import math
import os
import random
import re
import sys
import time

try:
    import mutagen
    from mutagen.mp4 import MP4Tags
except ImportError:
    print("Error: The 'mutagen' library is missing. Install it with: pip install mutagen")
    sys.exit(1)

# --- Configuration ---------------------------------------------------------

# Tempo scoring. Gaps are RELATIVE (percent) and symmetric. Half/double time counts as a match
# (70 vs 140 BPM is a gap of 0 %). The "OK" limit matches the sync window of midiAutoDJ.
BPM_GOOD_PERCENT = 4.0          # Gap up to this value: best tempo bonus
BPM_OK_PERCENT = 8.0            # Gap up to this value: smaller tempo bonus
BPM_MAX_PERCENT = 30.0          # Gap above this value: transition is practically forbidden (hard limit)

# Score values
SCORE_KEY_MATCH = 1000          # Harmonically compatible keys
SCORE_KEY_CLASH = -500          # Incompatible keys
SCORE_BPM_GOOD = 100
SCORE_BPM_OK = 50
SCORE_BPM_BAD = -10
SCORE_BPM_VARIATION = 10        # Prefer small tempo changes over exactly identical BPM
SCORE_BPM_LIMIT = -2000         # Transition above BPM_MAX_PERCENT

# Optional tempo trend: "none", "up" (slow to fast) or "down" (fast to slow).
# Adds TREND_BONUS to transitions in the wanted direction (only within the OK tempo window).
TEMPO_TREND = "none"
TREND_BONUS = 15

# --- Simulated Annealing Settings ---
SA_ITERATIONS_PER_TRACK = 4000  # Optimization steps per track and restart
SA_MIN_ITERATIONS = 200000      # Lower bound of steps per restart (small playlists)
SA_RESTARTS = 4                 # Independent runs, the best result is kept
SA_START_TEMP = 3000.0          # Start temperature (about the size of one key clash)
SA_END_TEMP = 1.0               # End temperature (practically greedy)
# ---------------------------------------------------------------------------

UNSORTED_MODES = ("separate", "append", "omit")


# --- Tag handling ----------------------------------------------------------

def parse_camelot(text):
    """Converts a Camelot key text (e.g. '8A', '08a', '8A - Energy 6') into (number, letter)."""
    if not text:
        return None
    words = str(text).strip().split()
    if not words:
        return None
    match = re.fullmatch(r"(\d{1,2})([AaBb])", words[0])
    if not match:
        return None
    number = int(match.group(1))
    if number < 1 or number > 12:
        return None
    return (number, match.group(2).upper())


def parse_bpm(text):
    """Converts a BPM tag value into a float. Returns None if it is not plausible."""
    try:
        bpm = float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if bpm < 20.0 or bpm > 400.0:
        return None
    return bpm


def frame_text(frame):
    """First text value of an ID3 frame, or None."""
    text = getattr(frame, "text", None)
    if text:
        return str(text[0])
    return None


def id3_candidates(tags):
    """Returns (bpm candidates, key candidates) of an ID3 tag, in priority order."""
    bpm_values = []
    key_values = []
    for frame in tags.getall("TBPM"):
        bpm_values.append(frame_text(frame))
    for frame in tags.getall("TXXX"):
        description = str(getattr(frame, "desc", "")).upper()
        if description == "BPM":
            bpm_values.append(frame_text(frame))
        elif description in ("KEY", "INITIALKEY"):
            key_values.append(frame_text(frame))
    # Camelot keys are usually written to the comment (Mixed In Key), so comments come first.
    comment_values = [frame_text(frame) for frame in tags.getall("COMM")]
    key_values = comment_values + [frame_text(frame) for frame in tags.getall("TKEY")] + key_values
    return bpm_values, key_values


def vorbis_candidates(tags):
    """Returns (bpm candidates, key candidates) of a Vorbis comment style tag (FLAC, OGG, Opus)."""
    bpm_values = list(tags.get("bpm") or [])
    key_values = []
    for name in ("comment", "description", "initialkey", "key"):
        key_values.extend(tags.get(name) or [])
    return bpm_values, key_values


def mp4_candidates(tags):
    """Returns (bpm candidates, key candidates) of an MP4/M4A tag."""
    bpm_values = [str(value) for value in (tags.get("tmpo") or [])]
    key_values = [str(value) for value in (tags.get("\xa9cmt") or [])]
    for name in tags.keys():
        if name.lower().startswith("----:com.apple.itunes:") and name.lower().endswith(("initialkey", ":key")):
            for value in tags[name]:
                key_values.append(bytes(value).decode("utf-8", errors="ignore"))
    return bpm_values, key_values


def read_track_metadata(abs_path):
    """Reads BPM and Camelot key. Returns (bpm, key_tuple, problem). problem is None on success."""
    if not os.path.isfile(abs_path):
        return None, None, "file not found"
    try:
        audio = mutagen.File(abs_path)
    except Exception as exc:  # Corrupt files raise many different exception types
        return None, None, "unreadable (%s)" % exc.__class__.__name__
    if audio is None:
        return None, None, "unsupported file format"
    tags = audio.tags
    if not tags:
        return None, None, "no tags"

    if hasattr(tags, "getall"):
        bpm_values, key_values = id3_candidates(tags)
    elif isinstance(tags, MP4Tags):
        bpm_values, key_values = mp4_candidates(tags)
    else:
        bpm_values, key_values = vorbis_candidates(tags)

    bpm = None
    for value in bpm_values:
        bpm = parse_bpm(value)
        if bpm is not None:
            break
    key_tuple = None
    for value in key_values:
        key_tuple = parse_camelot(value)
        if key_tuple is not None:
            break

    if bpm is None and key_tuple is None:
        return None, None, "no BPM and no Camelot key"
    if bpm is None:
        return None, key_tuple, "no usable BPM tag"
    if key_tuple is None:
        return bpm, None, "no Camelot key (first word of comment/TKEY)"
    return bpm, key_tuple, None


# --- Scoring ---------------------------------------------------------------

def is_harmonically_compatible(key1, key2):
    """
    Camelot Wheel compatibility.
    Rules: same key, +/- 1 hour on the wheel, or relative major/minor (A <-> B, same number).
    """
    num1, letter1 = key1
    num2, letter2 = key2
    if num1 == num2:
        return True  # Same key or relative major/minor
    if letter1 == letter2:
        if num2 == (num1 % 12) + 1:
            return True
        if num2 == ((num1 - 2 + 12) % 12) + 1:
            return True
    return False


def tempo_relation(bpm_a, bpm_b):
    """Returns (gap in percent, signed change in percent) using the best of 1x, 2x and 0.5x for b."""
    best_gap = None
    best_signed = 0.0
    for factor in (1.0, 2.0, 0.5):
        scaled = bpm_b * factor
        gap = abs(scaled - bpm_a) / min(bpm_a, scaled) * 100.0
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best_signed = (scaled - bpm_a) / bpm_a * 100.0
    return best_gap, best_signed


def transition_score(track_a, track_b):
    """Score of playing track_b after track_a (higher is better)."""
    gap, signed = tempo_relation(track_a["bpm"], track_b["bpm"])
    if gap > BPM_MAX_PERCENT:
        return SCORE_BPM_LIMIT

    if is_harmonically_compatible(track_a["key"], track_b["key"]):
        score = SCORE_KEY_MATCH
    else:
        score = SCORE_KEY_CLASH

    if gap <= BPM_GOOD_PERCENT:
        bpm_score = SCORE_BPM_GOOD
    elif gap <= BPM_OK_PERCENT:
        bpm_score = SCORE_BPM_OK
    else:
        bpm_score = SCORE_BPM_BAD
    if bpm_score > 0 and gap > 0.0:
        bpm_score += SCORE_BPM_VARIATION
    score += bpm_score

    if gap <= BPM_OK_PERCENT:
        if TEMPO_TREND == "up" and signed > 0.0:
            score += TREND_BONUS
        elif TEMPO_TREND == "down" and signed < 0.0:
            score += TREND_BONUS
    return score


def build_score_matrix(tracks):
    """matrix[i][j] is the score of playing track j directly after track i."""
    count = len(tracks)
    matrix = [[0.0] * count for _ in range(count)]
    for i in range(count):
        for j in range(count):
            if i != j:
                matrix[i][j] = float(transition_score(tracks[i], tracks[j]))
    return matrix


def is_symmetric(matrix):
    count = len(matrix)
    for i in range(count):
        for j in range(i + 1, count):
            if matrix[i][j] != matrix[j][i]:
                return False
    return True


def path_score(matrix, order):
    total = 0.0
    for k in range(len(order) - 1):
        total += matrix[order[k]][order[k + 1]]
    return total


# --- Simulated Annealing ---------------------------------------------------
# All move functions return the change of the TOTAL SCORE (higher is better) and evaluate only
# the transitions that actually change, so one step costs O(1) instead of O(n).

def swap_delta(matrix, order, i, j):
    """Swaps the tracks at positions i and j IN PLACE and returns the score change."""
    last = len(order) - 1
    positions = {i - 1, i, j - 1, j}
    before = 0.0
    for p in positions:
        if 0 <= p < last:
            before += matrix[order[p]][order[p + 1]]
    order[i], order[j] = order[j], order[i]
    after = 0.0
    for p in positions:
        if 0 <= p < last:
            after += matrix[order[p]][order[p + 1]]
    return after - before


def insert_delta(matrix, order, i, j):
    """Score change if the track at position i moved to final position j (nothing is modified)."""
    count = len(order)
    moved = order[i]
    left = order[i - 1] if i > 0 else -1
    right = order[i + 1] if i < count - 1 else -1

    delta = 0.0
    # Remove the track from its position
    if left >= 0:
        delta -= matrix[left][moved]
    if right >= 0:
        delta -= matrix[moved][right]
    if left >= 0 and right >= 0:
        delta += matrix[left][right]

    # Insert it at index j of the remaining list (rest[k] = order[k] for k < i, else order[k + 1])
    before_index = j - 1
    before = -1
    if before_index >= 0:
        before = order[before_index] if before_index < i else order[before_index + 1]
    after = -1
    if j < count - 1:
        after = order[j] if j < i else order[j + 1]
    if before >= 0 and after >= 0:
        delta -= matrix[before][after]
    if before >= 0:
        delta += matrix[before][moved]
    if after >= 0:
        delta += matrix[moved][after]
    return delta


def reverse_delta(matrix, order, i, j):
    """Score change if the segment i..j (i < j) was reversed. Only valid for symmetric matrices."""
    count = len(order)
    delta = 0.0
    if i > 0:
        delta += matrix[order[i - 1]][order[j]] - matrix[order[i - 1]][order[i]]
    if j < count - 1:
        delta += matrix[order[i]][order[j + 1]] - matrix[order[j]][order[j + 1]]
    return delta


def anneal(matrix, order, lo, hi, iterations, rng, symmetric, label):
    """
    Optimizes 'order' (list of track indices) in place and returns the best score found.
    Only positions lo..hi may move (positions outside are pinned).
    """
    current = path_score(matrix, order)
    best = current
    best_order = order[:]
    temp = SA_START_TEMP
    cooling = (SA_END_TEMP / SA_START_TEMP) ** (1.0 / iterations)
    progress_step = max(1, iterations // 10)

    for step in range(iterations):
        if step % progress_step == 0:
            sys.stdout.write("\r%s step %d/%d | best score %d   " % (label, step, iterations, int(best)))
            sys.stdout.flush()
        temp *= cooling

        roll = rng.random()
        i = rng.randint(lo, hi)
        j = rng.randint(lo, hi)
        if i == j:
            continue

        if roll < 0.4:
            # Swap two tracks (applied in place, reverted if rejected)
            delta = swap_delta(matrix, order, i, j)
            if delta >= 0.0 or rng.random() < math.exp(delta / temp):
                current += delta
            else:
                order[i], order[j] = order[j], order[i]
        elif roll < 0.8 or not symmetric:
            # Move one track to another position
            delta = insert_delta(matrix, order, i, j)
            if delta >= 0.0 or rng.random() < math.exp(delta / temp):
                order.insert(j, order.pop(i))
                current += delta
        else:
            # Reverse a segment (2-opt)
            if i > j:
                i, j = j, i
            delta = reverse_delta(matrix, order, i, j)
            if delta >= 0.0 or rng.random() < math.exp(delta / temp):
                order[i:j + 1] = order[i:j + 1][::-1]
                current += delta

        if current > best:
            best = current
            best_order = order[:]

    order[:] = best_order
    sys.stdout.write("\r%s done | best score %d                    \n" % (label, int(best)))
    sys.stdout.flush()
    return path_score(matrix, order)


def optimize(tracks, first_index, last_index, restarts, iterations_override, seed):
    """Returns the optimized list of tracks."""
    count = len(tracks)
    if count < 2:
        return list(tracks)

    matrix = build_score_matrix(tracks)
    symmetric = is_symmetric(matrix)
    rng = random.Random(seed)

    lo = 1 if first_index is not None else 0
    hi = count - 2 if last_index is not None else count - 1
    if hi - lo < 1:
        print("Nothing to optimize (fewer than two movable tracks).")
        order = list(range(count))
        return [tracks[k] for k in order]

    if iterations_override:
        iterations = iterations_override
    else:
        iterations = max(SA_MIN_ITERATIONS, count * SA_ITERATIONS_PER_TRACK)

    middle = [k for k in range(count) if k != first_index and k != last_index]
    best_order = None
    best_score = None
    print("Optimizing %d tracks (%d restarts x %d steps, seed %d)..." % (count, restarts, iterations, seed))
    for run in range(restarts):
        rng.shuffle(middle)
        order = ([first_index] if first_index is not None else []) + middle + \
                ([last_index] if last_index is not None else [])
        score = anneal(matrix, order, lo, hi, iterations, rng, symmetric, "Run %d/%d" % (run + 1, restarts))
        if best_score is None or score > best_score:
            best_score = score
            best_order = order[:]
    print("Best total score: %d" % int(best_score))
    return [tracks[k] for k in best_order]


# --- Playlist file handling ------------------------------------------------

def read_playlist(path):
    """
    Reads an M3U/M3U8 file. The encoding is detected (UTF-8 first, then Windows-1252/Latin-1)
    and returned, so the output can use the same one.
    Returns (paths, extinf_by_path, encoding, has_bom).
    """
    with open(path, "rb") as handle:
        raw = handle.read()
    has_bom = raw.startswith(codecs.BOM_UTF8)
    try:
        text = raw.decode("utf-8-sig")
        encoding = "utf-8"
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp1252")
            encoding = "cp1252"
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
            encoding = "latin-1"

    paths = []
    extinf = {}
    pending = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("#EXTINF"):
            pending = line
            continue
        if line.startswith("#"):
            continue
        if line not in extinf and line not in paths:
            paths.append(line)
            if pending:
                extinf[line] = pending
        pending = None
    return paths, extinf, encoding, has_bom


def rebase_path(entry, in_dir, out_dir):
    """Keeps relative entries valid if the output file lives in another directory."""
    if os.path.isabs(entry):
        return entry
    absolute = os.path.normpath(os.path.join(in_dir, entry))
    if os.path.normcase(os.path.abspath(in_dir)) == os.path.normcase(os.path.abspath(out_dir)):
        return entry
    try:
        return os.path.relpath(absolute, out_dir)
    except ValueError:  # Different drives on Windows
        return absolute


def write_playlist(path, entries, extinf, encoding, has_bom, in_dir, notes=None):
    """
    Writes an M3U file. 'notes' maps an entry to a plain ASCII text that is written as a comment
    line ('# ...') directly above the entry. Comment lines are ignored by Mixxx and other players.
    """
    out_dir = os.path.dirname(os.path.abspath(path))
    write_encoding = "utf-8-sig" if (encoding == "utf-8" and has_bom) else encoding
    with open(path, "w", encoding=write_encoding) as handle:
        handle.write("#EXTM3U\n")
        for entry in entries:
            if notes and entry in notes:
                handle.write("# " + notes[entry] + "\n")
            if entry in extinf:
                handle.write(extinf[entry] + "\n")
            handle.write(rebase_path(entry, in_dir, out_dir) + "\n")


def default_output_path(input_path):
    stem, extension = os.path.splitext(input_path)
    return stem + "_sorted" + extension


def unsorted_output_path(output_path):
    stem, extension = os.path.splitext(output_path)
    if stem.endswith("_sorted"):
        stem = stem[:-len("_sorted")]
    return stem + "_unsorted" + extension


# --- Main ------------------------------------------------------------------

def find_pinned(entries, text, label):
    """Finds the single entry whose path contains 'text' (case-insensitive). Exits on 0 or >1 hits."""
    needle = text.lower()
    hits = [entry for entry in entries if needle in entry.lower()]
    if not hits:
        print("Error: --%s '%s' matches no track in the playlist." % (label, text))
        sys.exit(2)
    if len(hits) > 1:
        print("Error: --%s '%s' is ambiguous, it matches:" % (label, text))
        for hit in hits:
            print("  " + hit)
        sys.exit(2)
    return hits[0]


def format_key(key):
    return "%d%s" % (key[0], key[1])


def weak_reasons(track_a, track_b):
    """Returns the reasons why the transition a -> b is weak (empty list if it is fine)."""
    reasons = []
    gap, _ = tempo_relation(track_a["bpm"], track_b["bpm"])
    if not is_harmonically_compatible(track_a["key"], track_b["key"]):
        reasons.append("key %s -> %s" % (format_key(track_a["key"]), format_key(track_b["key"])))
    if gap > BPM_MAX_PERCENT:
        reasons.append("tempo gap %.1f%% (%g -> %g BPM, above the %.0f%% limit)" %
                       (gap, track_a["bpm"], track_b["bpm"], BPM_MAX_PERCENT))
    elif gap > BPM_OK_PERCENT:
        reasons.append("tempo gap %.1f%% (%g -> %g BPM)" % (gap, track_a["bpm"], track_b["bpm"]))
    return reasons


def describe_weak_transitions(tracks):
    """Prints transitions that are not harmonically compatible or exceed the OK tempo window."""
    weak = []
    for k in range(len(tracks) - 1):
        reasons = weak_reasons(tracks[k], tracks[k + 1])
        if reasons:
            weak.append((k + 1, tracks[k], tracks[k + 1], reasons))
    print("Weak transitions: %d of %d" % (len(weak), max(0, len(tracks) - 1)))
    for position, a, b, reasons in weak[:15]:
        print("  #%d %s -> %s: %s" % (position, os.path.basename(a["path"]), os.path.basename(b["path"]),
                                      ", ".join(reasons)))
    if len(weak) > 15:
        print("  ... and %d more" % (len(weak) - 15))


def build_notes(sorted_tracks, unsorted):
    """Comment texts for the output playlists: key, tempo and weak transitions per track."""
    notes = {}
    for k, track in enumerate(sorted_tracks):
        text = "%d | %s | %g BPM" % (k + 1, format_key(track["key"]), track["bpm"])
        if k > 0:
            reasons = weak_reasons(sorted_tracks[k - 1], track)
            if reasons:
                text += " | WEAK transition from previous: " + ", ".join(reasons)
        notes[track["path"]] = text
    for entry, problem, bpm, key in unsorted:
        text = "not optimized: " + problem
        known = []
        if key is not None:
            known.append(format_key(key))
        if bpm is not None:
            known.append("%g BPM" % bpm)
        if known:
            text += " | known: " + ", ".join(known)
        notes[entry] = text
    return notes


def parse_arguments():
    parser = argparse.ArgumentParser(description="Harmonic playlist optimizer (Camelot Wheel + tempo).")
    parser.add_argument("input", help="Input playlist (.m3u / .m3u8)")
    parser.add_argument("output", nargs="?", help="Output playlist (default: <input>_sorted.<ext>)")
    parser.add_argument("--unsorted", choices=UNSORTED_MODES, default="separate",
                        help="Tracks that cannot be optimized: 'separate' = second playlist (default), "
                             "'append' = append to the sorted playlist, 'omit' = leave out")
    parser.add_argument("--first", metavar="TEXT", help="Pin the track whose path contains TEXT to the start")
    parser.add_argument("--last", metavar="TEXT", help="Pin the track whose path contains TEXT to the end")
    parser.add_argument("--trend", choices=("none", "up", "down"), default=None,
                        help="Prefer rising ('up') or falling ('down') tempo (default: %s)" % TEMPO_TREND)
    parser.add_argument("--restarts", type=int, default=SA_RESTARTS, help="Independent optimization runs")
    parser.add_argument("--iterations", type=int, default=0, help="Steps per run (default: depends on playlist size)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible results")
    parser.add_argument("--no-comments", action="store_true",
                        help="Do not write key/tempo comment lines ('# 8A | 128 BPM') into the playlists")
    return parser.parse_args()


def main():
    global TEMPO_TREND
    args = parse_arguments()
    if args.trend:
        TEMPO_TREND = args.trend
    output_path = args.output or default_output_path(args.input)
    seed = args.seed if args.seed is not None else int(time.time()) % 1000000

    in_dir = os.path.dirname(os.path.abspath(args.input))

    # 1. Read playlist
    try:
        entries, extinf, encoding, has_bom = read_playlist(args.input)
    except FileNotFoundError:
        print("Error: Input file '%s' not found." % args.input)
        sys.exit(1)
    print("Read %d unique tracks (encoding: %s)." % (len(entries), encoding))

    # 2. Read tags
    sortable = []
    unsorted = []
    for entry in entries:
        abs_path = entry if os.path.isabs(entry) else os.path.normpath(os.path.join(in_dir, entry))
        bpm, key, problem = read_track_metadata(abs_path)
        if problem is None:
            sortable.append({"path": entry, "bpm": bpm, "key": key})
        else:
            unsorted.append((entry, problem, bpm, key))
    print("Optimizable: %d | not optimizable: %d" % (len(sortable), len(unsorted)))
    if not sortable:
        print("Error: No track has a usable BPM and Camelot key tag.")
        sys.exit(1)

    # 3. Resolve pinned tracks
    first_index = None
    last_index = None
    sortable_paths = [track["path"] for track in sortable]
    for label, text in (("first", args.first), ("last", args.last)):
        if not text:
            continue
        hit = find_pinned(entries, text, label)
        if hit not in sortable_paths:
            print("Warning: --%s track has no usable tags and cannot be pinned: %s" % (label, hit))
            continue
        if label == "first":
            first_index = sortable_paths.index(hit)
        else:
            last_index = sortable_paths.index(hit)
    if first_index is not None and first_index == last_index:
        print("Error: --first and --last point to the same track.")
        sys.exit(2)

    # 4. Optimize
    sorted_tracks = optimize(sortable, first_index, last_index, max(1, args.restarts), args.iterations, seed)
    describe_weak_transitions(sorted_tracks)

    # 5. Write output
    sorted_entries = [track["path"] for track in sorted_tracks]
    unsorted_entries = [item[0] for item in unsorted]
    notes = None if args.no_comments else build_notes(sorted_tracks, unsorted)
    try:
        if args.unsorted == "append":
            write_playlist(output_path, sorted_entries + unsorted_entries, extinf, encoding, has_bom, in_dir, notes)
        else:
            write_playlist(output_path, sorted_entries, extinf, encoding, has_bom, in_dir, notes)
        print("Optimized playlist saved to: '%s'" % output_path)

        if unsorted and args.unsorted == "separate":
            unsorted_path = unsorted_output_path(output_path)
            write_playlist(unsorted_path, unsorted_entries, extinf, encoding, has_bom, in_dir, notes)
            print("Not optimized tracks saved to: '%s'" % unsorted_path)
    except OSError as exc:
        print("Error writing output: %s" % exc)
        sys.exit(1)

    if unsorted:
        action = {"separate": "second playlist", "append": "appended at the end", "omit": "omitted"}[args.unsorted]
        print("\nNot optimized tracks (%s):" % action)
        for entry, problem, _, _ in unsorted:
            print("  %s: %s" % (os.path.basename(entry), problem))


if __name__ == "__main__":
    main()
