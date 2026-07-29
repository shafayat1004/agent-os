"""Minimal YAML subset loader, standard library only.

Supported: block mappings, block sequences, flow lists and maps of scalars,
typed scalars, quoted strings, comments. Unsupported constructs raise YamlError.
Must-raise (never silently accepted): anchors, aliases, multi-document streams,
tab indentation, block literals (including chomping/indent variants like
|-, |+, >-, >+, |2, >2), and a nested block under a sequence-item inline mapping.
See the plan for the full subset definition.
"""


class YamlError(Exception):
    pass


def load(text):
    lines = _prepare(text)
    value, next_index = _parse_block(lines, 0)
    if next_index != len(lines):
        raise YamlError("trailing content at line %d" % (lines[next_index][0] + 1))
    return value


def _prepare(text):
    prepared_lines = []
    for line_number, raw_line in enumerate(text.splitlines()):
        leading = raw_line[: len(raw_line) - len(raw_line.lstrip(" \t"))]
        if "\t" in leading:
            raise YamlError("tab indentation at line %d" % (line_number + 1))
        without_comment = _strip_comment(raw_line)
        if without_comment.strip() == "":
            continue
        indent = len(without_comment) - len(without_comment.lstrip(" "))
        prepared_lines.append((line_number, indent, without_comment.strip()))
    return prepared_lines


def _strip_comment(line):
    kept_chars = []
    quote_char = None
    for char in line:
        if quote_char:
            kept_chars.append(char)
            if char == quote_char:
                quote_char = None
        elif char in ("'", '"'):
            quote_char = char
            kept_chars.append(char)
        elif char == "#":
            break
        else:
            kept_chars.append(char)
    return "".join(kept_chars)


def _parse_block(lines, index):
    if index >= len(lines):
        return None, index
    _, line_indent, content = lines[index]
    if content.startswith("- "):
        return _parse_sequence(lines, index, line_indent)
    return _parse_mapping(lines, index, line_indent)


def _parse_mapping(lines, index, block_indent):
    result = {}
    while index < len(lines):
        line_number, line_indent, content = lines[index]
        if line_indent < block_indent:
            break
        if line_indent > block_indent:
            raise YamlError("unexpected indentation at line %d" % (line_number + 1))
        if content.startswith("- "):
            raise YamlError("unexpected sequence item at line %d" % (line_number + 1))
        if ":" not in content:
            raise YamlError("expected 'key:' at line %d" % (line_number + 1))
        key, _, value_text = content.partition(":")
        key = key.strip()
        value_text = value_text.strip()
        if value_text == "":
            child_value, index = _parse_child(lines, index + 1, block_indent)
            result[key] = child_value
        else:
            result[key] = _scalar_or_flow(value_text, line_number)
            index += 1
    return result, index


def _parse_child(lines, index, parent_indent):
    if index >= len(lines):
        return None, index
    _, line_indent, _ = lines[index]
    if line_indent <= parent_indent:
        return None, index
    return _parse_block(lines, index)


def _parse_sequence(lines, index, block_indent):
    result = []
    while index < len(lines):
        line_number, line_indent, content = lines[index]
        if line_indent < block_indent or not content.startswith("- "):
            break
        if line_indent > block_indent:
            raise YamlError("unexpected indentation at line %d" % (line_number + 1))
        item_text = content[2:].strip()
        if _has_map_colon(item_text) and not item_text.startswith(("[", "{", '"', "'")):
            # inline first mapping key on the dash line
            mapping, index = _parse_inline_map_item(lines, index, block_indent, item_text)
            result.append(mapping)
        else:
            result.append(_scalar_or_flow(item_text, line_number))
            index += 1
    return result, index


def _has_map_colon(item):
    # A YAML mapping key ends with ": " or a trailing ":"; a bare scalar such
    # as a URL ("https://x") has a colon but no following space, so it is not
    # a mapping. Quotes are honored so ": " inside a quoted scalar is ignored.
    quote_char = None
    for position, char in enumerate(item):
        if quote_char:
            if char == quote_char:
                quote_char = None
        elif char in ("'", '"'):
            quote_char = char
        elif char == ":":
            if position == len(item) - 1 or item[position + 1] == " ":
                return True
    return False


def _parse_inline_map_item(lines, index, block_indent, first_item_text):
    line_number = lines[index][0]
    key, _, value_text = first_item_text.partition(":")
    mapping = {key.strip(): _scalar_or_flow(value_text.strip(), line_number)}
    index += 1
    child_indent = block_indent + 2
    while index < len(lines):
        child_line_number, line_indent, content = lines[index]
        if line_indent < child_indent or content.startswith("- "):
            break
        if line_indent > child_indent:
            raise YamlError(
                "nested block under sequence item not supported at line %d"
                % (child_line_number + 1))
        if ":" not in content:
            raise YamlError("expected 'key:' at line %d" % (child_line_number + 1))
        child_key, _, child_value = content.partition(":")
        mapping[child_key.strip()] = _scalar_or_flow(child_value.strip(), child_line_number)
        index += 1
    return mapping, index


def _scalar_or_flow(text, line_number):
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if inner == "":
            return []
        return [_scalar(part.strip(), line_number) for part in _split_flow(inner)]
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        mapping = {}
        if inner == "":
            return mapping
        for part in _split_flow(inner):
            key, _, value = part.partition(":")
            mapping[key.strip()] = _scalar(value.strip(), line_number)
        return mapping
    if _is_block_scalar_indicator(text):
        raise YamlError("block scalar not supported at line %d" % (line_number + 1))
    return _scalar(text, line_number)


def _is_block_scalar_indicator(text):
    if not text or text[0] not in "|>":
        return False
    suffix = text[1:]
    if len(suffix) > 2:
        return False
    digit_count = sum(1 for char in suffix if char.isdigit())
    sign_count = sum(1 for char in suffix if char in "+-")
    return digit_count <= 1 and sign_count <= 1 and digit_count + sign_count == len(suffix)


def _split_flow(inner):
    parts = []
    bracket_depth = 0
    quote_char = None
    buffer = []
    for char in inner:
        if quote_char:
            buffer.append(char)
            if char == quote_char:
                quote_char = None
        elif char in ("'", '"'):
            quote_char = char
            buffer.append(char)
        elif char in "[{":
            bracket_depth += 1
            buffer.append(char)
        elif char in "]}":
            bracket_depth -= 1
            buffer.append(char)
        elif char == "," and bracket_depth == 0:
            parts.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
    if buffer:
        parts.append("".join(buffer))
    return parts


def _scalar(text, line_number):
    if text == "":
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    if text[0] in ("&", "*"):
        raise YamlError("anchors/aliases not supported at line %d" % (line_number + 1))
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
