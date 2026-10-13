"""Assertion lines of one Test::More subtest, read lexically without Perl; structure, not proof of test semantics.

A bounded reader for authored `.t` files: it skips comments, quoted strings, quote-like operators (`q`, `qq`, `qw`,
`qr`, `m`, `s`, `tr`, `y` with any delimiter; paired delimiters nest) and `/.../` matches where an operand starts,
finds the one top-level `subtest NAME => sub { ... }` statement for the planned name and reports the line of each
Test::More assertion call its block makes (Test::More reports a failing call at the line where the call starts).
Calls inside a nested `sub` body do not count, since it runs only if called. Constructs it cannot track are refused
with a reason rather than guessed: POD, `__END__` or `__DATA__`, heredocs, `format`, and a file that defines or
aliases an assertion name.
"""

import re

# Test::More's checks that can fail on their own; `pass` never fails and `BAIL_OUT` stops the file instead.
ASSERTIONS = frozenset({"ok", "is", "isnt", "like", "unlike", "is_deeply", "cmp_ok", "can_ok", "isa_ok", "new_ok",
                        "fail"})
_NAMES = "|".join(sorted(ASSERTIONS))
REFUSED = (
    (re.compile(r"^=[A-Za-z]", re.MULTILINE), "POD block"),
    (re.compile(r"^__(?:END|DATA)__\b", re.MULTILINE), "__END__ or __DATA__"),
    (re.compile(r"^\s*format\b", re.MULTILINE), "format"),
    # A file that defines or aliases an assertion name could turn it into a no-op the reader still counts.
    (re.compile(r"\bsub\s+(?:\w+::)*(?:" + _NAMES + r")\b|\*(?:\w+::)*(?:" + _NAMES + r")\s*=(?!=)"),
     "definition of an assertion name"),
)
QUOTE_LIKE = {"q": 1, "qq": 1, "qw": 1, "qr": 1, "m": 1, "s": 2, "tr": 2, "y": 2}
PAIRS = {"(": ")", "[": "]", "{": "}", "<": ">"}
# After these tokens an operand starts, so `/` begins a match rather than a division.
OPERAND_AFTER = {None, "(", ",", "=", "=~", "!~", "{", ";", "!", "&&", "||", "//", "and", "or", "not", "return", "if",
                 "unless", "split", "grep", "map", "=>", "?", ":", "[", "x="} | ASSERTIONS
# Sigils join their name (`$s` is a variable, not a substitution) and punctuation variables (`$/`) their character.
TOKEN = re.compile(r"=>|->|=~|!~|&&|\|\||//|::|==|!=|<=|>=|\d[\w.]*|[A-Za-z_]\w*(?:::\w+)*"
                   r"|[$@%&][A-Za-z_]\w*(?:::\w+)*|\$#\w+|\$[^\s\w]|\S")
STRING = "<string>"


class _Lexer:
    """Tokens of code with their line numbers; literals become STRING tokens carrying their text."""

    def __init__(self, content: str):
        self.text, self.at, self.line = content, 0, 1
        self.tokens: list[tuple[str, int, str]] = []  # (token, line, literal text)

    def _advance(self, count: int) -> None:
        self.line += self.text.count("\n", self.at, self.at + count)
        self.at += count

    def _delimited(self, opener: str) -> str:
        """Skip from the opening delimiter at `at` past its close; paired delimiters nest. Returns the inner text."""
        close, start, depth = PAIRS.get(opener, opener), self.line, 0
        self._advance(1)
        begin = self.at
        while self.at < len(self.text):
            char = self.text[self.at]
            if char == "\\":
                self._advance(2)
            elif char == close and depth == 0:
                inner = self.text[begin:self.at]
                self._advance(1)
                return inner
            else:
                depth += (char == opener and opener != close) - (char == close and opener != close)
                self._advance(1)
        raise ValueError(f"unterminated literal starting at line {start}")

    def _skip_space(self) -> None:
        while self.at < len(self.text) and self.text[self.at].isspace():
            self._advance(1)

    def _quote_like(self, parts: int) -> str:
        self._skip_space()
        opener = self.text[self.at]
        text = self._delimited(opener)
        if parts == 2:
            if opener in PAIRS:
                self._skip_space()
                self._delimited(self.text[self.at])
            else:
                self.at -= 1  # The closing delimiter also opens the second part.
                self._delimited(opener)
        while self.at < len(self.text) and self.text[self.at].isalpha():
            self._advance(1)
        return text

    def tokens_of(self) -> list[tuple[str, int, str]]:
        while self.at < len(self.text):
            char = self.text[self.at]
            if char.isspace():
                self._advance(1)
                continue
            if char == "#":
                end = self.text.find("\n", self.at)
                self._advance((len(self.text) if end < 0 else end) - self.at)
                continue
            line = self.line
            previous = self.tokens[-1][0] if self.tokens else None
            if char in "'\"`":
                self.tokens.append((STRING, line, self._delimited(char)))
                continue
            if self.text.startswith("<<", self.at) and re.match(r"<<[~\"'A-Za-z_]", self.text[self.at:self.at + 3]):
                raise ValueError(f"heredoc at line {line}")
            if char == "/" and previous in OPERAND_AFTER and not self.text.startswith("//", self.at):
                self.tokens.append((STRING, line, self._delimited("/")))
                while self.at < len(self.text) and self.text[self.at].isalpha():
                    self._advance(1)
                continue
            token = TOKEN.match(self.text, self.at).group()
            following = self.text[self.at + len(token):].lstrip()
            if (token in QUOTE_LIKE and previous not in ("->", "sub", "{") and following
                    and not following[0].isalnum() and following[0] not in "_,;)=" and not following.startswith("=>")):
                self._advance(len(token))
                self.tokens.append((STRING, line, self._quote_like(QUOTE_LIKE[token])))
                continue
            self._advance(len(token))
            self.tokens.append((token, line, ""))
        return self.tokens


def _close(tokens, index: int) -> int:
    """Index of the bracket closing the one at `index`."""
    opener, depth = tokens[index][0], 0
    for at in range(index, len(tokens)):
        depth += (tokens[at][0] == opener) - (tokens[at][0] == PAIRS[opener])
        if depth == 0:
            return at
    raise ValueError(f"unbalanced {opener} at line {tokens[index][1]}")


def _blocks(tokens, name: str) -> list[tuple[int, int]]:
    """The token ranges of each top-level `subtest <name> => sub { ... }` block."""
    found, depth = [], 0
    for at, (token, _, text) in enumerate(tokens):
        if token in ("(", "[", "{"):
            depth += 1
        elif token in (")", "]", "}"):
            depth -= 1
        if depth or token not in ("subtest", "Test::More::subtest") or (at and tokens[at - 1][0] not in (";", "}")):
            continue
        first = at + 2 if at + 1 < len(tokens) and tokens[at + 1][0] == "(" else at + 1
        rest = tokens[first:first + 4]
        if (len(rest) == 4 and (rest[0][2] if rest[0][0] == STRING else rest[0][0]) == name
                and rest[1][0] in ("=>", ",") and rest[2][0] == "sub" and rest[3][0] == "{"):
            found.append((first + 3, _close(tokens, first + 3)))
    return found


def perl_assertion_lines(content: str, name: str) -> tuple[int, ...]:
    """Lines of the Test::More assertion calls the top-level subtest `name` makes; refused when not read reliably."""
    for pattern, construct in REFUSED:
        if pattern.search(content):
            raise ValueError(f"the test file uses {construct}, which the assertion reader does not follow")
    tokens = _Lexer(content).tokens_of()
    blocks = _blocks(tokens, name)
    if len(blocks) != 1:
        raise ValueError(f"expected exactly one top-level `subtest {name} => sub {{ ... }}`, found {len(blocks)}")
    start, end = blocks[0]
    lines, at = set(), start + 1
    while at < end:
        token, line, _ = tokens[at]
        if token == "sub":
            # A nested sub body runs only if called: skip to its close.
            brace = next((i for i in range(at + 1, end) if tokens[i][0] in ("{", ";")), end)
            at = _close(tokens, brace) + 1 if brace < end and tokens[brace][0] == "{" else at + 1
            continue
        previous = tokens[at - 1][0]
        following = tokens[at + 1][0] if at + 1 < end else None
        if token in ASSERTIONS and previous not in ("->", "&") and following != "=>":
            lines.add(line)
        at += 1
    return tuple(sorted(lines))


__all__ = ["ASSERTIONS", "perl_assertion_lines"]
