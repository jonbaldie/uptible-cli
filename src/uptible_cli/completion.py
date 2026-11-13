"""Local syntax discovery from the execution parser, without dispatch."""
import argparse
import os
import re
import shlex


def bash_words(line, point):
    raw = os.fsencode(line)
    if not 0 <= point <= len(raw) or len(raw) > 32768:
        raise ValueError("Invalid completion line")
    lexer = shlex.shlex(os.fsdecode(raw[:point]), posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    words = []
    trailing = True
    while True:
        try:
            word = lexer.get_token()
        except ValueError:
            words.append(lexer.token)
            break
        if word is None:
            if trailing:
                words.append("")
            break
        words.append(word)
        trailing = lexer.state == " "
    if not 1 < len(words) <= 256:
        raise ValueError("Invalid completion words")
    return words


def candidates(parser, previous, current):
    pending = None
    position = 0
    options = True
    for word in previous:
        if pending is not None:
            if pending.choices is not None and word not in map(str, pending.choices):
                return []
            pending = None
            continue
        if word == "--" and options:
            options = False
            continue
        if word.startswith("-") and options:
            name, equals, value = word.partition("=")
            action = parser._option_string_actions.get(name)
            if action is None:
                matches = [a for n, a in parser._option_string_actions.items() if n.startswith(name)]
                if not parser.allow_abbrev or not name.startswith("--") or len(matches) != 1:
                    return []
                action = matches[0]
            if action.nargs == 0:
                if equals or isinstance(action, (argparse._HelpAction, argparse._VersionAction)):
                    return []
            elif equals:
                if action.choices is not None and value not in map(str, action.choices):
                    return []
            else:
                pending = action
            continue
        positional = [a for a in parser._actions if not a.option_strings]
        if position >= len(positional):
            return []
        action = positional[position]
        if isinstance(action, argparse._SubParsersAction):
            if not options or word not in action.choices:
                return []
            parser = action.choices[word]
            position = 0
            options = True
        else:
            if action.choices is not None and word not in map(str, action.choices):
                return []
            position += 1
    prefix = ""
    if pending is not None:
        values = list(map(str, pending.choices)) if pending.choices is not None else []
    elif options and current.startswith("-"):
        name, equals, value = current.partition("=")
        if equals:
            action = parser._option_string_actions.get(name)
            if action is None or action.nargs == 0 or action.choices is None:
                return []
            prefix, current = name + "=", value
            values = list(map(str, action.choices))
        else:
            values = list(parser._option_string_actions)
    else:
        positional = [a for a in parser._actions if not a.option_strings]
        action = positional[position] if position < len(positional) else None
        if action is not None and action.choices is not None and (options or not isinstance(action, argparse._SubParsersAction)):
            values = list(map(str, action.choices))
        else:
            values = []
    return sorted(prefix + value for value in values
                  if value.startswith(current) and re.fullmatch(r"[A-Za-z0-9_.-]+", value))


def shell_script(shell):
    if shell == "bash":
        return '''_uptible_complete() {
    local candidate
    COMPREPLY=()
    while IFS= read -r candidate; do
        [[ -n $candidate ]] && COMPREPLY+=("$candidate")
    done < <(command uptible --_complete-bash "$COMP_POINT" "$COMP_LINE"; printf '\\n')
    if [[ $COMP_WORDBREAKS == *'='* && ${COMPREPLY[0]} == *=* ]]; then
        COMPREPLY=("${COMPREPLY[@]#*=}")
    fi
    return 0
}
complete -F _uptible_complete uptible
'''
    if shell == "zsh":
        return '''#compdef uptible
_uptible_complete() {
    local -a candidates
    candidates=("${(@f)$(command uptible --_complete "$((CURRENT - 1))" "${words[@]}")}")
    (( ${#candidates} )) && compadd -- "${candidates[@]}"
    return 0
}
compdef _uptible_complete uptible
'''
    raise ValueError("Unsupported completion shell")
