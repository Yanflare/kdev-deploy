#!/usr/bin/env python3
import os
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

SKILLS_DIR = Path("/home/yanflare/.kdev/skills")
ARCHIVE_DIR = Path("/home/yanflare/.kdev/skills_archive")
DAYS_OLD = 90
DRY_RUN = True  # Change to False only after you confirm the dry-run output

def get_file_age_days(file_path):
    return (datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)).days

def main():
    print("🔍 KDEV Phase 2B Pruning — Dry Run" if DRY_RUN else "🚀 KDEV Phase 2B Pruning — LIVE")
    old_skills = []
    for md_file in SKILLS_DIR.glob("*.md"):
        if get_file_age_days(md_file) > DAYS_OLD:
            old_skills.append(md_file)

    print(f"Found {len(old_skills)} skills older than {DAYS_OLD} days.")

    if not old_skills:
        print("✅ No skills need archiving today. Archive system is now active for future runs.")
        return

    # Group by month
    monthly_groups = {}
    for f in old_skills:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        month_key = mtime.strftime("%Y-%m")
        monthly_groups.setdefault(month_key, []).append(f)

    for month, files in monthly_groups.items():
        archive_name = ARCHIVE_DIR / f"skills_{month}.tar.gz"
        print(f"→ Archiving {len(files)} files → {archive_name.name}")
        if DRY_RUN:
            continue
        with tarfile.open(archive_name, "w:gz") as tar:
            for f in files:
                tar.add(f, arcname=f.name)
                # Remove after successful archive
                f.unlink()
        print(f"   Compressed and removed {len(files)} files")

    print("✅ Pruning complete." if not DRY_RUN else "✅ Dry-run complete — no files moved.")

if __name__ == "__main__":
    main()
