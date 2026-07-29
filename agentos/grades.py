_GRADES = {
    "state": "A-",
    "ledger": "A",
    "diff": "A",
    "deps": "B+",
    "skills": "B",
    "rules": "A-",
}


def grade_for(name: str) -> str:
    return _GRADES[name]
