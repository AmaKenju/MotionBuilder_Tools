# -*- coding: utf-8 -*-
# Replace a specific substring inside every Take name in the current scene.
# Compatible with both Python 2.7 (MotionBuilder <=2019) and Python 3.7+ (MotionBuilder 2022+).
from pyfbsdk import FBSystem

# ---------------------------------------------------------------------------
# Settings (edit these two lines, like the "Find & Replace" dialog):
#   FIND    = the text to search for      (検索)
#   REPLACE = the text to replace it with (置換後の文字列)
# ---------------------------------------------------------------------------
FIND = "old"
REPLACE = "new"

# If True, matching is case-insensitive.
CASE_INSENSITIVE = False
# If True, only print what would change without renaming anything.
DRY_RUN = False


def replace_substring(text, find, replace, case_insensitive):
    if not find:
        return text
    if not case_insensitive:
        return text.replace(find, replace)
    # Case-insensitive replace while preserving the surrounding text.
    result = []
    lower_text = text.lower()
    lower_find = find.lower()
    i = 0
    step = len(find)
    while True:
        idx = lower_text.find(lower_find, i)
        if idx == -1:
            result.append(text[i:])
            break
        result.append(text[i:idx])
        result.append(replace)
        i = idx + step
    return "".join(result)


def collect_existing_take_names(takes):
    return set(take.Name for take in takes)


def make_unique(base, existing):
    if base not in existing:
        existing.add(base)
        return base
    i = 1
    while True:
        candidate = "{0}{1}".format(base, i)
        if candidate not in existing:
            existing.add(candidate)
            return candidate
        i += 1


def rename_takes(find, replace, case_insensitive, dry_run):
    takes = list(FBSystem().Scene.Takes)
    if not takes:
        print("No takes found in the scene.")
        return 0

    existing = collect_existing_take_names(takes)
    changed = 0

    for take in takes:
        old_name = take.Name
        new_name = replace_substring(old_name, find, replace, case_insensitive)
        if new_name == old_name:
            continue

        # Avoid collisions with an already-existing take name.
        existing.discard(old_name)
        unique_name = make_unique(new_name, existing)

        if dry_run:
            print("[DRY RUN] '{0}' -> '{1}'".format(old_name, unique_name))
        else:
            take.Name = unique_name
            print("'{0}' -> '{1}'".format(old_name, unique_name))
        changed += 1

    return changed


changed = rename_takes(FIND, REPLACE, CASE_INSENSITIVE, DRY_RUN)
print("Done. {0} take(s) {1}.".format(
    changed, "would be renamed" if DRY_RUN else "renamed"))
