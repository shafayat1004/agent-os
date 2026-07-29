import subprocess


def changed_files(staged=False, rev_range=None):
    command = ["git", "diff", "--name-only"]
    if staged:
        command.append("--cached")
    if rev_range:
        command.append(rev_range)
    output = subprocess.check_output(command, text=True)
    return [line for line in output.splitlines() if line.strip()]
