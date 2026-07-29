"""Copy skeleton templates into a target repo, without overwriting.

Shared by `bin/bootstrap` and `agentos init`. The function returns the list
of created paths (its stable contract). Pass a `report` callback to observe
each action, including skips.
"""
import os
import shutil


def bootstrap(src_templates, dest, report=None):
    created = []
    for dirpath, _dirs, files in os.walk(src_templates):
        rel = os.path.relpath(dirpath, src_templates)
        target_dir = dest if rel == "." else os.path.join(dest, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in sorted(files):
            target = os.path.join(target_dir, name)
            if os.path.exists(target):
                if report:
                    report("skip existing", target)
                continue
            shutil.copy2(os.path.join(dirpath, name), target)
            created.append(target)
            if report:
                report("created", target)
    return created
