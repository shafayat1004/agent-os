"""Copy skeleton templates into a target repo, without overwriting.

Shared by `bin/bootstrap` and `agentos init`. The function returns the list
of created paths (its stable contract). Pass a `report` callback to observe
each action, including skips.
"""
import os
import shutil


def bootstrap(src_templates, dest, report=None):
    created = []
    for source_dir, _subdirs, files in os.walk(src_templates):
        relative_dir = os.path.relpath(source_dir, src_templates)
        target_dir = dest if relative_dir == "." else os.path.join(dest, relative_dir)
        os.makedirs(target_dir, exist_ok=True)
        for filename in sorted(files):
            target = os.path.join(target_dir, filename)
            if os.path.exists(target):
                if report:
                    report("skip existing", target)
                continue
            shutil.copy2(os.path.join(source_dir, filename), target)
            created.append(target)
            if report:
                report("created", target)
    return created
