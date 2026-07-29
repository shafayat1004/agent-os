import subprocess


def changed_files(staged=False, rev_range=None):
    cmd = ["git", "diff", "--name-only"]
    if staged:
        cmd.append("--cached")
    if rev_range:
        cmd.append(rev_range)
    out = subprocess.check_output(cmd, text=True)
    return [line for line in out.splitlines() if line.strip()]
