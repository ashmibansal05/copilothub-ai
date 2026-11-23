"""Maintenance commands.

    python -m app.maintenance --purge-orphans --dry-run   # show what would be removed
    python -m app.maintenance --purge-orphans             # remove files of deleted sessions
"""
import argparse

from app.db import session as db_session
from app.services import cleanup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--purge-orphans", action="store_true", help="remove upload folders / indexes of sessions that no longer exist")
    parser.add_argument("--dry-run", action="store_true", help="only list what would be removed")
    args = parser.parse_args()
    if not args.purge_orphans:
        parser.print_help()
        return

    with db_session.SessionLocal() as db:
        orphans = cleanup.find_orphans(db)
    if not orphans:
        print("No orphaned files.")
        return
    for path in orphans:
        print(("would remove: " if args.dry_run else "removing: ") + str(path))
    if not args.dry_run:
        print(f"Removed {cleanup.purge(orphans)} item(s).")


if __name__ == "__main__":
    main()