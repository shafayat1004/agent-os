"""Minimal YAML subset loader, standard library only.

Supported: block mappings, block sequences, flow lists and maps of scalars,
typed scalars, quoted strings, comments. Unsupported constructs raise YamlError.
See the plan for the full subset definition.
"""


class YamlError(Exception):
    pass


def load(text):
    lines = _prepare(text)
    value, idx = _parse_block(lines, 0, 0)
    if idx != len(lines):
        raise YamlError("trailing content at line %d" % (lines[idx][0] + 1))
    return value


def _prepare(text):
    out = []
    for n, raw in enumerate(text.splitlines()):
        if "\t" in raw[: len(raw) - len(raw.lstrip(" \t"))]:
            raise YamlError("tab indentation at line %d" % (n + 1))
        stripped = _strip_comment(raw)
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        out.append((n, indent, stripped.strip()))
    return out


def _strip_comment(line):
    out = []
    quote = None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out)


def _parse_block(lines, idx, indent):
    if idx >= len(lines):
        return None, idx
    _, cur_indent, content = lines[idx]
    if content.startswith("- "):
        return _parse_sequence(lines, idx, cur_indent)
    return _parse_mapping(lines, idx, cur_indent)


def _parse_mapping(lines, idx, indent):
    result = {}
    while idx < len(lines):
        n, cur_indent, content = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise YamlError("unexpected indentation at line %d" % (n + 1))
        if content.startswith("- "):
            raise YamlError("unexpected sequence item at line %d" % (n + 1))
        if ":" not in content:
            raise YamlError("expected 'key:' at line %d" % (n + 1))
        key, _, rest = content.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            child, idx = _parse_child(lines, idx + 1, indent)
            result[key] = child
        else:
            result[key] = _scalar_or_flow(rest, n)
            idx += 1
    return result, idx


def _parse_child(lines, idx, parent_indent):
    if idx >= len(lines):
        return None, idx
    n, cur_indent, _ = lines[idx]
    if cur_indent <= parent_indent:
        return None, idx
    return _parse_block(lines, idx, cur_indent)


def _parse_sequence(lines, idx, indent):
    result = []
    while idx < len(lines):
        n, cur_indent, content = lines[idx]
        if cur_indent < indent or not content.startswith("- "):
            break
        if cur_indent > indent:
            raise YamlError("unexpected indentation at line %d" % (n + 1))
        item = content[2:].strip()
        if ":" in item and not item.startswith(("[", "{", '"', "'")):
            # inline first mapping key on the dash line
            merged, idx = _parse_inline_map_item(lines, idx, indent, item)
            result.append(merged)
        else:
            result.append(_scalar_or_flow(item, n))
            idx += 1
    return result, idx


def _parse_inline_map_item(lines, idx, indent, first):
    n = lines[idx][0]
    key, _, rest = first.partition(":")
    mapping = {key.strip(): _scalar_or_flow(rest.strip(), n)}
    idx += 1
    child_indent = indent + 2
    while idx < len(lines):
        cn, cur_indent, content = lines[idx]
        if cur_indent < child_indent or content.startswith("- "):
            break
        if ":" not in content:
            raise YamlError("expected 'key:' at line %d" % (cn + 1))
        k, _, v = content.partition(":")
        mapping[k.strip()] = _scalar_or_flow(v.strip(), cn)
        idx += 1
    return mapping, idx


def _scalar_or_flow(text, n):
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if inner == "":
            return []
        return [_scalar(p.strip(), n) for p in _split_flow(inner)]
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        out = {}
        if inner == "":
            return out
        for part in _split_flow(inner):
            k, _, v = part.partition(":")
            out[k.strip()] = _scalar(v.strip(), n)
        return out
    if text in ("|", ">"):
        raise YamlError("block scalar not supported at line %d" % (n + 1))
    return _scalar(text, n)


def _split_flow(inner):
    parts = []
    depth = 0
    quote = None
    buf = []
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _scalar(text, n):
    if text == "":
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    if text in ("null", "~"):
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    try:
        return int(text)
    except ValueError:
        return text
