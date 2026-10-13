"""Version sets for SPEC-0042: a finite union of intervals over dotted numeric versions, plus the native
range syntaxes each ecosystem declares (PEP 440, npm semver, RubyGems, Maven, Perl). Deterministic and offline.

Versions are compared as integer tuples padded with zeros, so `3.7` is `3.7.0`. Pre-release and other
non-numeric qualifiers are refused by the parsers rather than guessed; callers record them as unparsed.
"""
from dataclasses import dataclass
import re
from typing import Iterable

Version = tuple[int, ...]
NUMERIC = re.compile(r'v?(\d+(?:\.\d+){0,3})')


class VersionSyntaxError(ValueError):
    pass


def parse_version(text: str) -> Version:
    match = NUMERIC.fullmatch(text.strip())
    if not match: raise VersionSyntaxError(f'not a numeric version: {text!r}')
    return tuple(int(part) for part in match[1].split('.'))


def render(version: Version) -> str:
    return '.'.join(map(str, version))


def _key(version: Version) -> Version:
    return version + (0,) * (4 - len(version))


def bump(version: Version) -> Version:
    """The first version after the series named by `version`: 3.7 -> 3.8, 14 -> 15."""
    return version[:-1] + (version[-1] + 1,)


@dataclass(frozen=True, order=True)
class Interval:
    lower: Version | None  # None: unbounded
    lower_inclusive: bool
    upper: Version | None
    upper_inclusive: bool

    def contains(self, version: Version) -> bool:
        k = _key(version)
        if self.lower is not None and (k < _key(self.lower) or (k == _key(self.lower) and not self.lower_inclusive)):
            return False
        if self.upper is not None and (k > _key(self.upper) or (k == _key(self.upper) and not self.upper_inclusive)):
            return False
        return True

    def empty(self) -> bool:
        if self.lower is None or self.upper is None: return False
        lo, hi = _key(self.lower), _key(self.upper)
        return lo > hi or (lo == hi and not (self.lower_inclusive and self.upper_inclusive))


def _intersect(a: Interval, b: Interval) -> Interval:
    if a.lower is None: lower = (b.lower, b.lower_inclusive)
    elif b.lower is None: lower = (a.lower, a.lower_inclusive)
    elif _key(a.lower) != _key(b.lower): lower = max((a.lower, a.lower_inclusive), (b.lower, b.lower_inclusive), key=lambda x: _key(x[0]))
    else: lower = (a.lower, a.lower_inclusive and b.lower_inclusive)
    if a.upper is None: upper = (b.upper, b.upper_inclusive)
    elif b.upper is None: upper = (a.upper, a.upper_inclusive)
    elif _key(a.upper) != _key(b.upper): upper = min((a.upper, a.upper_inclusive), (b.upper, b.upper_inclusive), key=lambda x: _key(x[0]))
    else: upper = (a.upper, a.upper_inclusive and b.upper_inclusive)
    return Interval(lower[0], lower[1], upper[0], upper[1])


@dataclass(frozen=True)
class VersionSet:
    intervals: tuple[Interval, ...]

    @classmethod
    def of(cls, intervals: Iterable[Interval]) -> 'VersionSet':
        kept = {i for i in intervals if not i.empty()}
        if any(i.lower is None and i.upper is None for i in kept):
            return cls((Interval(None, False, None, False),))
        kept = sorted(kept,
                      key=lambda i: (i.lower is not None, _key(i.lower) if i.lower else ()))
        return cls(tuple(kept))

    def contains(self, version: Version) -> bool:
        return any(i.contains(version) for i in self.intervals)

    def intersect(self, other: 'VersionSet') -> 'VersionSet':
        return VersionSet.of(_intersect(a, b) for a in self.intervals for b in other.intervals)

    def union(self, other: 'VersionSet') -> 'VersionSet':
        return VersionSet.of(self.intervals + other.intervals)

    @property
    def is_empty(self) -> bool:
        return not self.intervals

    @property
    def is_any(self) -> bool:
        return self.intervals == (Interval(None, False, None, False),)

    @property
    def lowest(self) -> Version | None:
        bounds = [i.lower for i in self.intervals]
        return None if not bounds or None in bounds else min(bounds, key=_key)

    def __str__(self) -> str:
        if self.is_any: return '*'
        if self.is_empty: return '(none)'
        parts = []
        for i in self.intervals:
            if i.lower is not None and i.upper is not None and i.lower_inclusive and not i.upper_inclusive and bump(i.lower) == i.upper:
                parts.append(f'{render(i.lower)}.*')
            elif i.lower is not None and i.upper is not None and i.lower_inclusive and i.upper_inclusive and _key(i.lower) == _key(i.upper):
                parts.append(f'=={render(i.lower)}')
            else:
                bounds = ([f'{">=" if i.lower_inclusive else ">"}{render(i.lower)}'] if i.lower is not None else []) + \
                         ([f'{"<=" if i.upper_inclusive else "<"}{render(i.upper)}'] if i.upper is not None else [])
                parts.append(','.join(bounds))
        return ' || '.join(parts)


ANY = VersionSet((Interval(None, False, None, False),))
NONE = VersionSet(())


def exactly(version: Version) -> VersionSet:
    return VersionSet((Interval(version, True, version, True),))


def series(version: Version) -> VersionSet:
    """Every release in the named series: `3.7` is 3.7.x, `14` is 14.x, `3.7.4` is exactly 3.7.4's patch series."""
    return VersionSet((Interval(version, True, bump(version), False),))


def at_least(version: Version) -> VersionSet:
    return VersionSet((Interval(version, True, None, False),))


def _comparator(op: str, version: Version, wildcard: bool = False) -> VersionSet:
    if wildcard:
        if op in ('==', '='): return series(version)
        if op == '!=': return VersionSet.of([Interval(None, False, version, False), Interval(bump(version), True, None, False)])
        raise VersionSyntaxError(f'wildcard with {op}')
    return {
        '>=': VersionSet((Interval(version, True, None, False),)),
        '>': VersionSet((Interval(version, False, None, False),)),
        '<=': VersionSet((Interval(None, False, version, True),)),
        '<': VersionSet((Interval(None, False, version, False),)),
        '==': exactly(version), '=': exactly(version), '===': exactly(version),
        '!=': VersionSet.of([Interval(None, False, version, False), Interval(version, False, None, False)]),
    }[op]


PEP440 = re.compile(r'\s*(~=|===|==|!=|<=|>=|<|>)\s*v?(\d+(?:\.\d+)*)(\.\*)?\s*')


def pep440(text: str) -> VersionSet:
    """A PEP 440 specifier set such as `>=3.6, !=3.0.*, <4`; pre/post/local segments are refused."""
    result = ANY
    for clause in filter(None, (c.strip() for c in text.split(','))):
        match = PEP440.fullmatch(clause)
        if not match: raise VersionSyntaxError(f'unsupported PEP 440 clause {clause!r}')
        op, version, wildcard = match[1], tuple(int(p) for p in match[2].split('.')), bool(match[3])
        if op == '~=':
            if len(version) < 2: raise VersionSyntaxError('~= needs two components')
            clause_set = VersionSet((Interval(version, True, bump(version[:-1]), False),))
        else:
            clause_set = _comparator(op, version, wildcard)
        result = result.intersect(clause_set)
    return result


def _npm_partial(text: str) -> tuple[Version, int]:
    """(numeric prefix, number of given components); x, X and * end the prefix."""
    parts = text.lstrip('v=').split('.')
    given = []
    for part in parts:
        if part in ('x', 'X', '*', ''): break
        if not part.isdigit(): raise VersionSyntaxError(f'unsupported npm version {text!r}')
        given.append(int(part))
    return tuple(given), len(given)


def _npm_simple(token: str) -> VersionSet:
    match = re.fullmatch(r'(\^|~|>=|<=|>|<|=)?\s*(.+)', token)
    op, rest = match[1] or '', match[2]
    version, given = _npm_partial(rest)
    if given == 0: return ANY if op in ('', '=', '>=', '^', '~') else NONE if op == '<' else ANY
    if op == '^':
        nonzero = next((i for i, part in enumerate(version) if part != 0), given - 1)
        return VersionSet((Interval(version, True, bump(version[:nonzero + 1]), False),))
    if op == '~':
        return VersionSet((Interval(version, True, bump(version[:2] if given >= 2 else version), False),))
    if given < 3 and op in ('', '='): return series(version)
    if given < 3 and op == '>': return VersionSet((Interval(bump(version), True, None, False),))
    if given < 3 and op == '<=': return VersionSet((Interval(None, False, bump(version), False),))
    return _comparator(op or '=', version)


def npm(text: str) -> VersionSet:
    """An npm semver range: `||` alternatives of comparators, hyphen ranges, ^, ~ and x-ranges."""
    result = NONE
    for alternative in text.split('||'):
        alternative = re.sub(r'(>=|<=|>|<|=|\^|~)\s+', r'\1', alternative.strip())
        if (hyphen := re.fullmatch(r'(\S+)\s+-\s+(\S+)', alternative)):
            low, _ = _npm_partial(hyphen[1])
            high, given = _npm_partial(hyphen[2])
            upper = VersionSet((Interval(None, False, high, True),)) if given >= 3 else \
                VersionSet((Interval(None, False, bump(high), False),)) if given else ANY
            alt = (at_least(low) if low else ANY).intersect(upper)
        else:
            alt = ANY
            for token in alternative.split():
                alt = alt.intersect(_npm_simple(token))
        result = result.union(alt)
    return result


GEM = re.compile(r'\s*(~>|>=|<=|!=|=|>|<)?\s*(\d+(?:\.\d+)*)\s*')


def gem(clauses: Iterable[str]) -> VersionSet:
    """A RubyGems requirement list such as `('>= 2.3', '< 4')`; `~> 2.5` is >= 2.5, < 3."""
    result = ANY
    for clause in clauses:
        match = GEM.fullmatch(clause)
        if not match: raise VersionSyntaxError(f'unsupported gem requirement {clause!r}')
        op, version = match[1] or '=', tuple(int(p) for p in match[2].split('.'))
        if op == '~>':
            stem = version[:-1] if len(version) > 1 else version
            clause_set = VersionSet((Interval(version, True, bump(stem), False),))
        else:
            clause_set = _comparator(op, version)
        result = result.intersect(clause_set)
    return result


MAVEN_RANGE = re.compile(r'([\[(])\s*([^,\[\]()]*)\s*(?:,\s*([^,\[\]()]*)\s*)?([\])])')


def maven(text: str, normalise=lambda v: v) -> VersionSet:
    """A Maven version range (`[1.8,)`, `(,11]`, unions) or a bare version, which Maven treats as a minimum
    in enforcer rules; `normalise` maps each bound (for example Java's `1.8` to `8`)."""
    text = text.strip()
    if not text.startswith(('[', '(')):
        return at_least(normalise(parse_version(text)))
    result, position = NONE, 0
    while position < len(text):
        match = MAVEN_RANGE.match(text, position)
        if not match: raise VersionSyntaxError(f'unsupported Maven range {text!r}')
        low, high = match[2].strip(), match[3]
        if high is None:  # [1.8] is exact
            version = normalise(parse_version(low))
            clause = exactly(version)
        else:
            clause = VersionSet((Interval(normalise(parse_version(low)) if low else None, match[1] == '[',
                                          normalise(parse_version(high.strip())) if high.strip() else None,
                                          match[4] == ']'),))
        result = result.union(clause)
        position = match.end()
        while position < len(text) and text[position] in ', ': position += 1
    return result


def perl(text: str) -> Version:
    """Perl's decimal (`5.008001`) or dotted (`v5.8.1`, `5.8.1`) version as a dotted tuple."""
    text = text.strip().strip('\'"')
    if text.startswith('v') or text.count('.') > 1: return parse_version(text)
    whole, _, fraction = text.partition('.')
    if not whole.isdigit() or (fraction and not fraction.isdigit()): raise VersionSyntaxError(f'not a Perl version: {text!r}')
    fraction = fraction.ljust(((len(fraction) + 2) // 3) * 3, '0')
    return (int(whole), *(int(fraction[i:i + 3]) for i in range(0, len(fraction), 3))) if fraction else (int(whole),)


def java_feature(version: Version) -> Version:
    """Java's legacy `1.8` naming to feature release `8`."""
    return version[1:2] if version[:1] == (1,) and len(version) > 1 else version[:1]


def parse_set(text: str) -> VersionSet:
    """Inverse of `str(VersionSet)`: the canonical form stored in requirement contracts."""
    text = text.strip()
    if text == '*': return ANY
    if text == '(none)': return NONE
    result = NONE
    for part in text.split(' || '):
        if part.endswith('.*'):
            result = result.union(series(parse_version(part[:-2])))
        elif part.startswith('=='):
            result = result.union(exactly(parse_version(part[2:])))
        else:
            clause = ANY
            for bound in part.split(','):
                match = re.fullmatch(r'(>=|>|<=|<)(\d+(?:\.\d+)*)', bound)
                if not match: raise VersionSyntaxError(f'not a canonical version set: {text!r}')
                clause = clause.intersect(_comparator(match[1], parse_version(match[2])))
            result = result.union(clause)
    return result
