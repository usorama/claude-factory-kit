"""Write the small TOML the factory uses (strings, numbers, booleans, lists, one level of tables).
The standard library reads TOML (tomllib) but cannot write it."""
import json


def value(item):
    if isinstance(item, bool):
        return "true" if item else "false"
    if isinstance(item, (int, float)):
        return repr(item)
    if isinstance(item, list):
        return "[" + ", ".join(value(x) for x in item) + "]"
    return json.dumps(str(item), ensure_ascii=False)


def dumps(data, comment=""):
    lines = [f"# {line}" for line in comment.splitlines()]
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    lines += [f"{k} = {value(v)}" for k, v in data.items() if k not in tables]
    for name, table in tables.items():
        plain = {k: v for k, v in table.items() if not isinstance(v, dict)}
        if plain:  # a table header first, so these keys cannot fall into an earlier table
            lines += ["", f"[{name}]"] + [f"{k} = {value(v)}" for k, v in plain.items()]
        for sub, body in table.items():
            if isinstance(body, dict):
                lines += ["", f"[{name}.{sub}]"] + [f"{k} = {value(v)}" for k, v in body.items()]
    return "\n".join(lines) + "\n"
