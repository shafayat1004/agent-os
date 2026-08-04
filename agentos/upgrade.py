"""`agentos upgrade`: refresh the vendored runtime from a release tarball.

Fetches a release tarball from GitHub via urllib (stdlib only), extracts
it, and atomically replaces the runtime files in `.agent-os/` (bin/,
agentos/, schemas/, VERSION). User-owned files are never touched:
AGENTS.md, STATE.yaml, evidence/, policies/, skills/, .claude/settings.json,
.opencode/plugins/agentos.js, and .agent-os/hooks/ extension directories.

`agentos upgrade --check` compares the local VERSION against the latest
release tag and reports only, without downloading or modifying anything.
"""
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request

_GITHUB_API = "https://api.github.com/repos/shafayat1004/agent-os/releases"
_GITHUB_DOWNLOAD = "https://github.com/shafayat1004/agent-os/releases/download"


def _local_version(vendor_dir):
    """Read the local VERSION file from the vendored runtime."""
    path = os.path.join(vendor_dir, "VERSION")
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        return handle.read().strip()


def _latest_release():
    """Fetch the latest release tag from the GitHub API."""
    url = _GITHUB_API + "/latest"
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "agentos-upgrade",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data.get("tag_name"), data.get("html_url")


def _download_tarball(tag, dest_path):
    """Download the release tarball for a given tag."""
    url = "%s/%s/agentos-%s.tar.gz" % (_GITHUB_DOWNLOAD, tag, tag)
    request = urllib.request.Request(url, headers={
        "User-Agent": "agentos-upgrade",
    })
    with urllib.request.urlopen(request, timeout=120) as response:
        with open(dest_path, "wb") as handle:
            shutil.copyfileobj(response, handle)


def _extract_runtime(tarball_path, vendor_dir, report):
    """Extract the tarball and replace runtime files in .agent-os/.

    The tarball is expected to contain bin/, agentos/, schemas/, VERSION
    at its top level. Extension directories under .agent-os/hooks/ are
    preserved (never deleted).
    """
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    runtime_names = ("bin", "agentos", "schemas", "VERSION")
    with tempfile.TemporaryDirectory() as extract_dir:
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(extract_dir)
        # Find the runtime root inside the tarball (may be nested).
        source_root = extract_dir
        for name in os.listdir(extract_dir):
            candidate = os.path.join(extract_dir, name)
            if os.path.isdir(candidate) and os.path.exists(
                    os.path.join(candidate, "bin")):
                source_root = candidate
                break
        # Remove old runtime files (not extension dirs).
        for name in runtime_names:
            dst = os.path.join(vendor_dir, name)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            elif os.path.exists(dst):
                os.remove(dst)
        # Copy new runtime files.
        for name in runtime_names:
            src = os.path.join(source_root, name)
            if not os.path.exists(src):
                continue
            dst = os.path.join(vendor_dir, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, ignore=ignore)
            else:
                shutil.copy2(src, dst)
            report("refreshed", dst)
        # Ensure .gitignore exists.
        gitignore_path = os.path.join(vendor_dir, ".gitignore")
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, "w") as handle:
                handle.write("__pycache__/\n*.pyc\n")
            report("created", gitignore_path)
        # Ensure extension dirs exist.
        for ext_name in ("pre-tool.d", "post-tool.d", "stop.d"):
            ext_path = os.path.join(vendor_dir, "hooks", ext_name)
            os.makedirs(ext_path, exist_ok=True)
            gitkeep = os.path.join(ext_path, ".gitkeep")
            if not os.path.exists(gitkeep):
                with open(gitkeep, "w") as handle:
                    pass


def run_upgrade(target_dir, to_version=None, check_only=False, report=None):
    """Refresh the vendored runtime in <target_dir>/.agent-os/.

    Returns a dict with keys: action, local_version, latest_version,
    upgraded_to, message.
    """
    report = report or (lambda action, path: None)
    vendor_dir = os.path.join(target_dir, ".agent-os")
    if not os.path.isdir(vendor_dir):
        return {"action": "noop", "local_version": None,
                "latest_version": None, "upgraded_to": None,
                "message": "no vendored runtime at .agent-os/; run "
                           "'agentos init' first"}

    local = _local_version(vendor_dir)
    if check_only:
        try:
            latest, url = _latest_release()
        except Exception as error:
            return {"action": "error", "local_version": local,
                    "latest_version": None, "upgraded_to": None,
                    "message": "cannot fetch latest release: %s" % error}
        if latest and local:
            if local == latest.lstrip("v"):
                msg = "up to date: %s" % local
            else:
                msg = "update available: %s -> %s" % (local, latest)
        else:
            msg = "local: %s, latest: %s" % (local, latest)
        return {"action": "check", "local_version": local,
                "latest_version": latest, "upgraded_to": None,
                "message": msg}

    tag = to_version or _latest_release()[0]
    if tag is None:
        return {"action": "error", "local_version": local,
                "latest_version": None, "upgraded_to": None,
                "message": "cannot determine latest release tag"}
    if not tag.startswith("v"):
        tag = "v" + tag

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tarball_path = tmp.name
    try:
        _download_tarball(tag, tarball_path)
        _extract_runtime(tarball_path, vendor_dir, report)
    except Exception as error:
        return {"action": "error", "local_version": local,
                "latest_version": tag, "upgraded_to": None,
                "message": "upgrade failed: %s" % error}
    finally:
        os.unlink(tarball_path)

    new_version = _local_version(vendor_dir)
    return {"action": "upgraded", "local_version": local,
            "latest_version": tag, "upgraded_to": new_version,
            "message": "upgraded %s -> %s" % (local, new_version)}
