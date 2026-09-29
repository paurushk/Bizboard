"""Shared least-loaded tie-break. Callers own the lock and the count query."""


def pick_least_loaded(members, load_counts):
    if not members:
        return None
    return min(members, key=lambda member: (load_counts.get(member.id, 0), member.id))
