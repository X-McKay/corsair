"""Assertion lines of one Minitest method, read lexically without Ruby; structure, not proof of test semantics.

A bounded reader for authored Minitest files: it skips comments, strings, heredocs, `%` literals, symbols, labels
and regular expressions, tracks the keywords that close with `end` to find `def <method>` in the planned class, and
reports the start line of each assertion call the method body makes (Ruby reports a failing call at the line where
the call starts). Calls in blocks inside the method count; calls in a nested `def` do not. Constructs it cannot
track are refused with a reason rather than guessed: `=begin` blocks, `__END__` and endless method definitions.
"""

import re

ASSERTION = re.compile(r"(?:assert|refute)(?:_\w+)?[?!]?|must_\w+|wont_\w+|flunk")
REFUSED = (
    (re.compile(r"^=begin\b", re.MULTILINE), "=begin block"),
    (re.compile(r"^__END__\s*$", re.MULTILINE), "__END__"),
)
CONDITIONAL = {"if", "unless", "while", "until", "for"}
# A conditional keyword opens a block only where a statement or expression starts.
STATEMENT_START = {None, ";", "=", "(", "[", "{", ",", "||", "&&", "!", "and", "or", "not", "then", "else",
                   "do", "begin", "+=", "-=", "||=", "&&=", "|"}
# After these tokens an operand starts, so `/`, `%` and `?` begin a literal rather than an operator.
OPERAND_AFTER = STATEMENT_START | {"==", "=~", "!~", "!=", "<", ">", "<=", ">=", "+", "-", "*", "?", ":", "<<",
                                   "when", "if", "unless", "while", "until", "elsif", "in", "return", "puts", "p"}
PAIRS = {"(": ")", "[": "]", "{": "}", "<": ">"}
HEREDOC = re.compile(r"<<([~-]?)(['\"`]?)([A-Za-z_]\w*)\2")
PERCENT = re.compile(r"%([qQwWiIrsx]?)([^\w\s])")
TOKEN = re.compile(r"\|\|=|&&=|\+=|-=|==|=~|!~|!=|<=|>=|\|\||&&|<<|::|&\.|[A-Za-z_]\w*[?!]?|@{1,2}\w+|\$\w+"
                   r"|\d[\w.]*|\S")


class _Lexer:
    """Tokens of code with their line numbers; literals become placeholder tokens."""

    def __init__(self, content: str):
        self.text, self.at, self.line = content, 0, 1
        self.tokens: list[tuple[str, int]] = []
        self.heredocs: list[tuple[bool, str]] = []  # (indented terminator allowed, terminator) awaiting a newline

    def _advance(self, count: int) -> None:
        self.line += self.text.count("\n", self.at, self.at + count)
        self.at += count

    def _literal(self, opener: str, close: str, interpolates: bool) -> None:
        """Skip from the opening delimiter at `at` to its close; paired delimiters nest."""
        start, depth = self.line, 0
        self._advance(1)
        while self.at < len(self.text):
            char = self.text[self.at]
            if char == "\\":
                self._advance(2)
            elif char == close and depth == 0:
                self._advance(1)
                return
            elif interpolates and self.text.startswith("#{", self.at):
                self._advance(2)
                self._code(until="}")
            else:
                depth += (char == opener and opener != close) - (char == close)
                self._advance(1)
        raise ValueError(f"unterminated literal starting at line {start}")

    def _heredoc_bodies(self) -> None:
        """At the start of a line after heredoc openers: skip each body through its terminator line."""
        for indented, terminator in self.heredocs:
            while True:
                if self.at >= len(self.text):
                    raise ValueError(f"heredoc {terminator} is not terminated")
                end = self.text.find("\n", self.at)
                end = len(self.text) if end < 0 else end
                body = self.text[self.at:end]
                self._advance(end - self.at + (end < len(self.text)))
                if (body.strip() if indented else body.rstrip("\r")) == terminator:
                    break
        self.heredocs = []

    def _previous(self) -> str | None:
        if not self.tokens or self.tokens[-1][0] == "\n":
            return None
        return self.tokens[-1][0]

    def _operand_here(self) -> bool:
        """A literal can start: after an operator, or after a bare method name and a space with none following."""
        previous = self._previous()
        if previous in OPERAND_AFTER:
            return True
        before, after = self.text[self.at - 1:self.at], self.text[self.at + 1:self.at + 2]
        return bool(re.fullmatch(r"[a-z_]\w*[?!]?", previous or "") and before in " \t" and after not in " \t=")

    def _code(self, until: str | None = None) -> None:
        depth = 0
        while self.at < len(self.text):
            char, rest = self.text[self.at], self.text[self.at:self.at + 3]
            if char == "\n":
                self.tokens.append(("\n", self.line))
                self._advance(1)
                if self.heredocs:
                    self._heredoc_bodies()
            elif char.isspace():
                self._advance(1)
            elif char == "#":
                end = self.text.find("\n", self.at)
                self._advance((len(self.text) if end < 0 else end) - self.at)
            elif char in "'\"`":
                self._literal(char, char, interpolates=char != "'")
                self.tokens.append(("<string>", self.line))
            elif rest.startswith("<<") and (heredoc := HEREDOC.match(self.text, self.at)) and (
                    heredoc.group(1) or heredoc.group(2) or self._operand_here() or self._previous() in {"(", ","}):
                self.heredocs.append((bool(heredoc.group(1)), heredoc.group(3)))
                self._advance(heredoc.end() - self.at)
                self.tokens.append(("<string>", self.line))
            elif char == "/" and self._operand_here():
                self._literal("/", "/", interpolates=True)
                self._advance(len(re.match(r"[imxounse]*", self.text[self.at:]).group()))
                self.tokens.append(("<regex>", self.line))
            elif char == "%" and (percent := PERCENT.match(self.text, self.at)) and self._operand_here():
                kind, opener = percent.groups()
                self._advance(1 + len(kind))
                self._literal(opener, PAIRS.get(opener, opener), interpolates=kind in {"", "Q", "W", "I", "r", "x"})
                if kind == "r":
                    self._advance(len(re.match(r"[imxounse]*", self.text[self.at:]).group()))
                self.tokens.append(("<string>", self.line))
            elif char == "?" and self._operand_here() and re.match(r"\?(\\.|[^\s\\])(?![\w?])", self.text[self.at:]):
                self._advance(2 + (self.text[self.at + 1] == "\\"))
                self.tokens.append(("<string>", self.line))
            elif char == ":" and (symbol := re.match(r":(?:[A-Za-z_]\w*[?!=]?|\[\]=?|[+\-*/<>=!~%&|^]+)", self.text[self.at:])) \
                    and self.text[self.at - 1:self.at] != ":" and not rest.startswith("::"):
                if self.text[self.at + 1] in "\"'":
                    self._advance(1)
                    self._literal(self.text[self.at], self.text[self.at], interpolates=self.text[self.at] == '"')
                else:
                    self._advance(symbol.end())
                self.tokens.append(("<symbol>", self.line))
            elif char == ":" and self.text[self.at + 1:self.at + 2] in "\"'":
                self._advance(1)
                self._literal(self.text[self.at], self.text[self.at], interpolates=self.text[self.at] == '"')
                self.tokens.append(("<symbol>", self.line))
            else:
                if until and char == "{":
                    depth += 1
                elif until and char == until:
                    if depth == 0:
                        self._advance(1)
                        return
                    depth -= 1
                token = TOKEN.match(self.text, self.at).group()
                self._advance(len(token))
                # `if: 1` or `end:` in a hash or keyword argument is a label, never a keyword.
                if re.fullmatch(r"[A-Za-z_]\w*[?!]?", token) and self.text[self.at:self.at + 1] == ":" and \
                        self.text[self.at + 1:self.at + 2] != ":":
                    self._advance(1)
                    token = "<label>"
                self.tokens.append((token, self.line))
        if until:
            raise ValueError("unterminated interpolation")

    def tokenize(self) -> list[tuple[str, int]]:
        self._code()
        return self.tokens


def _statement_start(tokens: list[tuple[str, int]], index: int) -> bool:
    previous = tokens[index - 1][0] if index else None
    return previous in STATEMENT_START or previous == "\n"


def _line_after(tokens: list[tuple[str, int]], index: int) -> list[str]:
    rest = []
    for token, _ in tokens[index + 1:]:
        if token == "\n":
            break
        rest.append(token)
    return rest


def _endless(signature: list[str]) -> bool:
    """`def name(args) = expr` or `def name = expr`: a method without `end`."""
    if signature[1:2] == ["."]:
        signature = signature[2:]  # def receiver.name
    if len(signature) > 1 and signature[1] == "(":
        depth = 0
        for position, token in enumerate(signature[1:], 1):
            depth += (token == "(") - (token == ")")
            if depth == 0:
                return signature[position + 1:position + 2] == ["="]
        return False
    return signature[1:2] == ["="]


def _qualified(stack: list[tuple[str, str | None, str | None]]) -> str | None:
    return next((name for _, name, _ in reversed(stack) if name), None)


def ruby_assertion_lines(content: str, class_name: str, method: str) -> tuple[int, ...]:
    """Start lines of the assertion calls that `class_name#method` makes; ValueError when they cannot be read."""
    for pattern, construct in REFUSED:
        found = pattern.search(content)
        if found:
            line = content.count("\n", 0, found.start()) + 1
            raise ValueError(f"test file uses a {construct} at line {line}, which the assertion check cannot read; "
                             "write the test without it")
    tokens = _Lexer(content).tokenize()
    # A name assigned anywhere in the file (`assert_msg = ...`) is a local variable where it appears bare.
    variables = {token for index, (token, _) in enumerate(tokens[:-1])
                 if tokens[index + 1][0] in {"=", "||=", "&&=", "+=", "-="} and (index == 0 or tokens[index - 1][0] != ".")}
    # Open blocks closed by `end`: (keyword, qualified name of a class or module, method name of a def).
    stack: list[tuple[str, str | None, str | None]] = []
    loop_header = False  # inside `while`/`until`/`for` before its line ends: an optional `do` opens nothing
    lines: set[int] = set()
    definitions = 0
    for index, (token, line) in enumerate(tokens):
        previous = tokens[index - 1][0] if index else None
        if token == "\n":
            loop_header = False
            continue
        if previous in {".", "&."}:
            pass  # a call on a receiver; `_(x).must_equal` is still an assertion below
        elif token in {"class", "module"}:
            following = _line_after(tokens, index)
            if following[:1] == ["<<"]:
                stack.append((token, None, None))  # class << self
                continue
            name = "".join(next(iter([following[:position] for position, part in enumerate(following)
                                      if not (re.fullmatch(r"[A-Z]\w*", part) or part == "::")]), following))
            outer = _qualified(stack)
            qualified = name.lstrip(":") if not outer or name.startswith("::") else f"{outer}::{name}"
            stack.append((token, qualified or None, None))
            continue
        elif token == "def":
            signature = _line_after(tokens, index)
            if _endless(signature):
                raise ValueError(f"test file uses an endless method definition at line {line}, which the "
                                 "assertion check cannot read; write the test without it")
            name = signature[0] if signature else ""
            if stack and stack[-1][1] == class_name and name == method:
                definitions += 1
            stack.append(("def", None, name))
            continue
        elif token in {"begin", "case"}:
            stack.append((token, None, None))
            continue
        elif token == "do":
            if not loop_header:
                stack.append((token, None, None))
            loop_header = False
            continue
        elif token in CONDITIONAL and _statement_start(tokens, index):
            stack.append((token, None, None))
            loop_header = token in {"while", "until", "for"}
            continue
        elif token == "end":
            if not stack:
                raise ValueError(f"unmatched end at line {line}")
            stack.pop()
            continue
        if ASSERTION.fullmatch(token) and previous != "def" and (token not in variables or previous in {".", "&."}):
            methods = [entry for entry in stack if entry[0] == "def"]
            # Only the method body itself: a nested def runs only if called.
            if len(methods) == 1 and methods[0][2] == method and _qualified(stack) == class_name:
                lines.add(line)
    if stack:
        raise ValueError(f"test file has {len(stack)} unclosed block(s)")
    if definitions != 1:
        raise ValueError(f"{class_name}#{method} is " + ("not defined in its test file" if not definitions
                                                          else "defined more than once in its test file"))
    return tuple(sorted(lines))


__all__ = ["ruby_assertion_lines"]
