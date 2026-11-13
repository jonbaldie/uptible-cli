"""Local syntax discovery from the execution parser, without dispatch."""
import argparse
import re


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
    local candidate word
    local -a query
    local index=0 i
    query=("${COMP_WORDS[0]}")
    for ((i=1; i<=COMP_CWORD; i++)); do
        word=${COMP_WORDS[i]}
        if [[ ( $word == = || $word == : ) && $i -gt 1 ]]; then
            query[index]="${query[index]}$word"
        elif [[ $i -gt 1 && ( ${COMP_WORDS[i-1]} == = || ${COMP_WORDS[i-1]} == : ) ]]; then
            query[index]="${query[index]}$word"
        else
            ((index+=1))
            query[index]=$word
        fi
    done
    COMPREPLY=()
    while IFS= read -r candidate; do
        [[ -n $candidate ]] && COMPREPLY+=("$candidate")
    done < <(command uptible --_complete "$index" "${query[@]}"; printf '\\n')
    if [[ $COMP_WORDBREAKS == *'='* && ${query[index]} == *=* ]]; then
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
