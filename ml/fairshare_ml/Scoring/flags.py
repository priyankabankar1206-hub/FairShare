from datetime import timedelta

import pandas as pd

MAX_TINY_LINES = 5
MIN_RUN = 5
MAX_GAP = timedelta(minutes=30)

LINE_COLUMNS = ["code_lines", "test_lines", "doc_lines"]


def split_commit_members(commits: pd.DataFrame) -> set[str]:
    """
    Members who broke work into a burst of tiny commits.

    A member is flagged when they have MIN_RUN or more commits in a row that
    each add 1 to MAX_TINY_LINES lines and come within MAX_GAP of the one
    before. Any bigger commit of theirs ends the run. It is a heuristic: it
    shows a pattern for a human to look at, it does not prove anything.

    Input : the commits that count as work, with member_id, author_date
            (timezone-aware) and code_lines, test_lines, doc_lines.
    Output: the set of member_ids to flag.
    """
    added = commits[LINE_COLUMNS].sum(axis=1)
    flagged: set[str] = set()

    for member_id, rows in commits.assign(added=added).groupby("member_id"):
        run, previous = 0, None
        for date, lines in sorted(zip(rows["author_date"], rows["added"]), key=lambda pair: pair[0]):
            if not 0 < lines <= MAX_TINY_LINES:
                run, previous = 0, None
                continue
            run = run + 1 if previous is not None and date - previous <= MAX_GAP else 1
            previous = date
            if run >= MIN_RUN:
                flagged.add(member_id)
                break
    return flagged