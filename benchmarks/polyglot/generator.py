"""Deterministically generate the Corsair polyglot security-regression fixtures.

The generated trees are deliberately small and self-contained.  A case directory is
one finding/payload variant with a vulnerable and fixed source revision.  Each
revision is a runnable example, so 11 families x 5 payload variants x 2 revisions
is 110 runnable revision-variants per language.  They are synthetic policy
templates, not claims of real vulnerable frameworks or distinct CVEs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from corsair.kernel import Hypothesis, Submission

GENERATOR_VERSION = "polyglot/2"
LANGUAGES = ("python", "java", "javascript", "typescript", "perl", "ruby", "cpp")


@dataclass(frozen=True)
class Family:
    slug: str
    title: str
    cwe: str
    root_cause: str
    expected_violation: str
    control: str
    exploits: tuple[str, str, str, str, str]


# Payloads are raw process arguments. A generated probe applies one independently
# rendered, value-derived fixed-policy invariant to both its control and exploit inputs.
FAMILIES = (
    Family("path-sibling-prefix", "Path containment accepts a sibling prefix", "CWE-22",
           "The path check tests a lexical public prefix instead of canonical containment below public/.",
           "an input outside the public subtree is accepted", "public/readme.txt",
           ("publicity/secret.txt", "public/../private.txt", "public/../../private.txt",
            "public../private.txt", "public_backup/credentials.txt")),
    Family("authorization-missing-owner", "Authorization omits resource ownership", "CWE-862",
           "The authorization decision only checks that an owner field exists, not that it matches the requester.",
           "a requester is authorized for another principal's resource", "alice:alice",
           ("alice:bob", "alice:carol", "admin:guest", "bob:alice", "service:root")),
    Family("negative-amount", "Negative amount bypasses balance bound", "CWE-20",
           "The amount is bounded above but a negative debit is not rejected before the balance comparison.",
           "a negative monetary amount is accepted", "12", ("-1", "-50", "-999", "-101", "-2147483648")),
    Family("integer-boundary", "Integer range omits maximum", "CWE-190",
           "The numeric input is checked for non-negativity but not for the maximum permitted allocation.",
           "an over-limit integer is accepted", "99", ("100", "1000", "999999999", "2147483648", "1000000000000")),
    Family("url-hostname-suffix", "URL host check accepts a hostname suffix", "CWE-918",
           "The URL authority is searched for an approved hostname rather than comparing the parsed hostname exactly.",
           "a URL controlled by an unapproved host is accepted", "https://api.example.test/v1",
           ("https://api.example.test.attacker.test/x", "https://api.example.test@attacker.test/x",
            "https://evilapi.example.test/x", "https://attacker.api.example.test/x",
            "https://api.example.test:443@attacker.test/x")),
    Family("command-argument-validation", "Command argument policy accepts option-like input", "CWE-78",
           "The command wrapper accepts an unvalidated argument token; it never invokes a shell or external command.",
           "an unsafe command argument token is accepted", "report",
           ("--output=/tmp/pwn", "-rf", "report;touch", "report name", "report/../../etc/passwd")),
    Family("object-property-pollution", "Reserved object property key is accepted", "CWE-1321",
           "A user-controlled property key is accepted without excluding prototype-like reserved names where applicable.",
           "a reserved object/property key is accepted", "theme",
           ("__proto__", "constructor", "prototype", "__defineGetter__", "__defineSetter__")),
    Family("header-crlf", "Header value accepts CRLF", "CWE-113",
           "The header value is accepted without rejecting carriage-return or newline control characters.",
           "a CRLF-bearing header value is accepted", "hello",
           ("hello\r\nX-Injected: 1", "\nSet-Cookie: x", "\rBad: yes", "\r\nSet-Cookie: session=x", "good\nX-Injected: yes")),
    Family("filename-extension-case", "Filename extension policy accepts misleading case or suffix", "CWE-434",
           "The upload policy searches for .pdf anywhere and case-folds it instead of requiring the final lowercase extension.",
           "a filename outside the allowed .pdf extension policy is accepted", "report.pdf",
           ("report.pdf.exe", "report.PDF", "report.pdf ", "report.pdf%00.exe", "report.pdf/evil")),
    Family("token-expiry-boundary", "Token expiry accepts the exact boundary", "CWE-613",
           "The token check treats expiry equal to the current instant as valid instead of requiring a future expiry.",
           "an expired-at-boundary token is accepted", "1001|1000",
           ("1000|1000", "0|0", "2147483647|2147483647", "-1|-1", "100|100")),
    Family("redirect-absolute-network-path", "Redirect accepts absolute or network-path target", "CWE-601",
           "The redirect policy accepts absolute and network-path references instead of restricting redirects to one local path.",
           "an absolute or network-path redirect target is accepted", "/account",
           ("https://attacker.test/x", "//attacker.test/x", "\\attacker.test\\x", "http://attacker.test/x", "ftp://attacker.test/x")),
)

FAMILY_BY_SLUG = {family.slug: family for family in FAMILIES}


def _quoted(value: str) -> str:
    """A portable JSON string literal, suitable for all generated languages here."""
    return json.dumps(value, ensure_ascii=False)


def _python_policy(family: str, safe: bool) -> str:
    return f'''FAMILY = {_quoted(family)}
SAFE = {safe!r}


def allowed(value: str) -> bool:
    if FAMILY == "path-sibling-prefix":
        return value.startswith("public/") and ".." not in value if SAFE else value.startswith("public")  # TARGET: path-sibling-prefix
    if FAMILY == "authorization-missing-owner":
        parts = value.split(":", 1)
        return len(parts) == 2 and (parts[0] == parts[1] if SAFE else bool(parts[1]))  # TARGET: authorization-missing-owner
    if FAMILY == "negative-amount":
        try:
            amount = int(value)
        except ValueError:
            return False
        return 0 <= amount <= 100 if SAFE else amount <= 100  # TARGET: negative-amount
    if FAMILY == "integer-boundary":
        try:
            amount = int(value)
        except ValueError:
            return False
        return 0 <= amount <= 99 if SAFE else amount >= 0  # TARGET: integer-boundary
    if FAMILY == "url-hostname-suffix":
        authority = value.split("://", 1)[-1].split("/", 1)[0]
        host = authority.rsplit("@", 1)[-1].split(":", 1)[0].lower()
        return host == "api.example.test" if SAFE else "api.example.test" in authority.lower()  # TARGET: url-hostname-suffix
    if FAMILY == "command-argument-validation":
        return value.replace("_", "").isalnum() if SAFE else bool(value)  # TARGET: command-argument-validation
    if FAMILY == "object-property-pollution":
        return value not in {{"__proto__", "constructor", "prototype", "__defineGetter__", "__defineSetter__"}} if SAFE else bool(value)  # TARGET: object-property-pollution
    if FAMILY == "header-crlf":
        return "\\r" not in value and "\\n" not in value if SAFE else bool(value)  # TARGET: header-crlf
    if FAMILY == "filename-extension-case":
        return value.endswith(".pdf") if SAFE else ".pdf" in value.lower()  # TARGET: filename-extension-case
    if FAMILY == "token-expiry-boundary":
        try:
            expiry, now = (int(part) for part in value.split("|", 1))
        except ValueError:
            return False
        return expiry > now if SAFE else expiry >= now  # TARGET: token-expiry-boundary
    if FAMILY == "redirect-absolute-network-path":
        return value.startswith("/") and not value.startswith("//") and not value.startswith(chr(92)) if SAFE else (value.startswith("/") or "://" in value or value.startswith(chr(92)))  # TARGET: redirect-absolute-network-path
    return False
'''


def _java_policy(family: str, safe: bool) -> str:
    return f'''package bench;

public final class Policy {{
    private static final String FAMILY = {_quoted(family)};
    private static final boolean SAFE = {str(safe).lower()};

    private static Long number(String value) {{
        try {{ return Long.valueOf(value); }} catch (NumberFormatException error) {{ return null; }}
    }}

    public static boolean allowed(String value) {{
        if (FAMILY.equals("path-sibling-prefix"))
            return SAFE ? value.startsWith("public/") && !value.contains("..") : value.startsWith("public"); // TARGET: path-sibling-prefix
        if (FAMILY.equals("authorization-missing-owner")) {{
            String[] parts = value.split(":", 2);
            return parts.length == 2 && (SAFE ? parts[0].equals(parts[1]) : !parts[1].isEmpty()); // TARGET: authorization-missing-owner
        }}
        if (FAMILY.equals("negative-amount")) {{
            Long amount = number(value); if (amount == null) return false;
            return SAFE ? amount >= 0 && amount <= 100 : amount <= 100; // TARGET: negative-amount
        }}
        if (FAMILY.equals("integer-boundary")) {{
            Long amount = number(value); if (amount == null) return false;
            return SAFE ? amount >= 0 && amount <= 99 : amount >= 0; // TARGET: integer-boundary
        }}
        if (FAMILY.equals("url-hostname-suffix")) {{
            String authority = value.replaceFirst("^[^:]+://", "").split("/", 2)[0];
            String host = authority.contains("@") ? authority.substring(authority.lastIndexOf('@') + 1) : authority;
            host = host.split(":", 2)[0].toLowerCase();
            return SAFE ? host.equals("api.example.test") : authority.toLowerCase().contains("api.example.test"); // TARGET: url-hostname-suffix
        }}
        if (FAMILY.equals("command-argument-validation"))
            return SAFE ? value.matches("[A-Za-z0-9_]+") : !value.isEmpty(); // TARGET: command-argument-validation
        if (FAMILY.equals("object-property-pollution"))
            return SAFE ? !(value.equals("__proto__") || value.equals("constructor") || value.equals("prototype") || value.equals("__defineGetter__") || value.equals("__defineSetter__")) : !value.isEmpty(); // TARGET: object-property-pollution
        if (FAMILY.equals("header-crlf"))
            return SAFE ? !(value.contains("\\r") || value.contains("\\n")) : !value.isEmpty(); // TARGET: header-crlf
        if (FAMILY.equals("filename-extension-case"))
            return SAFE ? value.endsWith(".pdf") : value.toLowerCase().contains(".pdf"); // TARGET: filename-extension-case
        if (FAMILY.equals("token-expiry-boundary")) {{
            String[] parts = value.split("\\\\|", 2); if (parts.length != 2) return false;
            Long expiry = number(parts[0]), now = number(parts[1]); if (expiry == null || now == null) return false;
            return SAFE ? expiry > now : expiry >= now; // TARGET: token-expiry-boundary
        }}
        if (FAMILY.equals("redirect-absolute-network-path"))
            return SAFE ? value.startsWith("/") && !value.startsWith("//") && !value.startsWith("\\\\") : value.startsWith("/") || value.contains("://") || value.startsWith("\\\\"); // TARGET: redirect-absolute-network-path
        return false;
    }}
}}
'''


def _js_policy(family: str, safe: bool, *, typescript: bool) -> str:
    flag = str(safe).lower()
    annotation = ": string" if typescript else ""
    return f'''const FAMILY{annotation} = {_quoted(family)};
const SAFE = {flag};

function number(value{annotation}) {{
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}}

export function allowed(value{annotation}) {{
  if (FAMILY === "path-sibling-prefix")
    return SAFE ? value.startsWith("public/") && !value.includes("..") : value.startsWith("public"); // TARGET: path-sibling-prefix
  if (FAMILY === "authorization-missing-owner") {{
    const parts = value.split(":", 2);
    return parts.length === 2 && (SAFE ? parts[0] === parts[1] : Boolean(parts[1])); // TARGET: authorization-missing-owner
  }}
  if (FAMILY === "negative-amount") {{
    const amount = number(value); if (amount === null) return false;
    return SAFE ? amount >= 0 && amount <= 100 : amount <= 100; // TARGET: negative-amount
  }}
  if (FAMILY === "integer-boundary") {{
    const amount = number(value); if (amount === null) return false;
    return SAFE ? amount >= 0 && amount <= 99 : amount >= 0; // TARGET: integer-boundary
  }}
  if (FAMILY === "url-hostname-suffix") {{
    const authority = value.replace(/^[^:]+:\\/\\//, "").split("/", 1)[0];
    const host = (authority.split("@").at(-1) ?? "").split(":", 1)[0].toLowerCase();
    return SAFE ? host === "api.example.test" : authority.toLowerCase().includes("api.example.test"); // TARGET: url-hostname-suffix
  }}
  if (FAMILY === "command-argument-validation")
    return SAFE ? /^[A-Za-z0-9_]+$/.test(value) : Boolean(value); // TARGET: command-argument-validation
  if (FAMILY === "object-property-pollution")
    return SAFE ? !["__proto__", "constructor", "prototype", "__defineGetter__", "__defineSetter__"].includes(value) : Boolean(value); // TARGET: object-property-pollution
  if (FAMILY === "header-crlf")
    return SAFE ? !(value.includes("\\r") || value.includes("\\n")) : Boolean(value); // TARGET: header-crlf
  if (FAMILY === "filename-extension-case")
    return SAFE ? value.endsWith(".pdf") : value.toLowerCase().includes(".pdf"); // TARGET: filename-extension-case
  if (FAMILY === "token-expiry-boundary") {{
    const parts = value.split("|", 2); const expiry = number(parts[0]); const now = number(parts[1]);
    if (parts.length !== 2 || expiry === null || now === null) return false;
    return SAFE ? expiry > now : expiry >= now; // TARGET: token-expiry-boundary
  }}
  if (FAMILY === "redirect-absolute-network-path")
    return SAFE ? value.startsWith("/") && !value.startsWith("//") && !value.startsWith("\\\\") : value.startsWith("/") || value.includes("://") || value.startsWith("\\\\"); // TARGET: redirect-absolute-network-path
  return false;
}}
'''


def _ruby_policy(family: str, safe: bool) -> str:
    return f'''FAMILY = {_quoted(family)}
SAFE = {str(safe).lower()}

module VulnApp
  module_function

  def number(value)
    Integer(value)
  rescue ArgumentError
    nil
  end

  def allowed(value)
    if FAMILY == "path-sibling-prefix"
      return SAFE ? value.start_with?("public/") && !value.include?("..") : value.start_with?("public") # TARGET: path-sibling-prefix
    end
    if FAMILY == "authorization-missing-owner"
      parts = value.split(":", 2)
      return parts.length == 2 && (SAFE ? parts[0] == parts[1] : !parts[1].empty?) # TARGET: authorization-missing-owner
    end
    if FAMILY == "negative-amount"
      amount = number(value); return false if amount.nil?
      return SAFE ? amount >= 0 && amount <= 100 : amount <= 100 # TARGET: negative-amount
    end
    if FAMILY == "integer-boundary"
      amount = number(value); return false if amount.nil?
      return SAFE ? amount >= 0 && amount <= 99 : amount >= 0 # TARGET: integer-boundary
    end
    if FAMILY == "url-hostname-suffix"
      authority = value.split("://", 2).last.split("/", 2).first
      host = authority.split("@").last.split(":", 2).first.downcase
      return SAFE ? host == "api.example.test" : authority.downcase.include?("api.example.test") # TARGET: url-hostname-suffix
    end
    if FAMILY == "command-argument-validation"
      return SAFE ? !!(value =~ /\\A[A-Za-z0-9_]+\\z/) : !value.empty? # TARGET: command-argument-validation
    end
    if FAMILY == "object-property-pollution"
      return SAFE ? !["__proto__", "constructor", "prototype", "__defineGetter__", "__defineSetter__"].include?(value) : !value.empty? # TARGET: object-property-pollution
    end
    if FAMILY == "header-crlf"
      return SAFE ? !value.include?("\\r") && !value.include?("\\n") : !value.empty? # TARGET: header-crlf
    end
    if FAMILY == "filename-extension-case"
      return SAFE ? value.end_with?(".pdf") : value.downcase.include?(".pdf") # TARGET: filename-extension-case
    end
    if FAMILY == "token-expiry-boundary"
      parts = value.split("|", 2); return false unless parts.length == 2
      expiry = number(parts[0]); now = number(parts[1]); return false if expiry.nil? || now.nil?
      return SAFE ? expiry > now : expiry >= now # TARGET: token-expiry-boundary
    end
    if FAMILY == "redirect-absolute-network-path"
      return SAFE ? value.start_with?("/") && !value.start_with?("//") && !value.start_with?("\\\\") : value.start_with?("/") || value.include?("://") || value.start_with?("\\\\") # TARGET: redirect-absolute-network-path
    end
    false
  end
end
'''


def _perl_policy(family: str, safe: bool) -> str:
    flag = 1 if safe else 0
    return f'''package VulnApp;
use strict;
use warnings;
our $FAMILY = {_quoted(family)};
our $SAFE = {flag};

sub number {{
    my ($value) = @_;
    return undef unless $value =~ /\\A-?\\d+\\z/;
    return int($value);
}}

sub allowed {{
    my ($value) = @_;
    if ($FAMILY eq "path-sibling-prefix") {{
        return $SAFE ? (index($value, "public/") == 0 && index($value, "..") < 0) : index($value, "public") == 0; # TARGET: path-sibling-prefix
    }}
    if ($FAMILY eq "authorization-missing-owner") {{
        my @parts = split(/:/, $value, 2);
        return @parts == 2 && ($SAFE ? $parts[0] eq $parts[1] : length($parts[1]) > 0); # TARGET: authorization-missing-owner
    }}
    if ($FAMILY eq "negative-amount") {{
        my $amount = number($value); return 0 unless defined $amount;
        return $SAFE ? ($amount >= 0 && $amount <= 100) : $amount <= 100; # TARGET: negative-amount
    }}
    if ($FAMILY eq "integer-boundary") {{
        my $amount = number($value); return 0 unless defined $amount;
        return $SAFE ? ($amount >= 0 && $amount <= 99) : $amount >= 0; # TARGET: integer-boundary
    }}
    if ($FAMILY eq "url-hostname-suffix") {{
        my $authority = $value; $authority =~ s/^[^:]+:\\/\\///; $authority = (split(/\\//, $authority, 2))[0];
        my $host = (split(/\\@/, $authority))[-1]; $host = (split(/:/, $host, 2))[0]; $host = lc($host);
        return $SAFE ? $host eq "api.example.test" : index(lc($authority), "api.example.test") >= 0; # TARGET: url-hostname-suffix
    }}
    if ($FAMILY eq "command-argument-validation") {{
        return $SAFE ? $value =~ /\\A[A-Za-z0-9_]+\\z/ : length($value) > 0; # TARGET: command-argument-validation
    }}
    if ($FAMILY eq "object-property-pollution") {{
        return $SAFE ? !($value eq "__proto__" || $value eq "constructor" || $value eq "prototype" || $value eq "__defineGetter__" || $value eq "__defineSetter__") : length($value) > 0; # TARGET: object-property-pollution
    }}
    if ($FAMILY eq "header-crlf") {{
        return $SAFE ? (index($value, "\\r") < 0 && index($value, "\\n") < 0) : length($value) > 0; # TARGET: header-crlf
    }}
    if ($FAMILY eq "filename-extension-case") {{
        return $SAFE ? $value =~ /\\.pdf\\z/ : index(lc($value), ".pdf") >= 0; # TARGET: filename-extension-case
    }}
    if ($FAMILY eq "token-expiry-boundary") {{
        my @parts = split(/\\|/, $value, 2); return 0 unless @parts == 2;
        my $expiry = number($parts[0]); my $now = number($parts[1]); return 0 unless defined $expiry && defined $now;
        return $SAFE ? $expiry > $now : $expiry >= $now; # TARGET: token-expiry-boundary
    }}
    if ($FAMILY eq "redirect-absolute-network-path") {{
        return $SAFE ? (index($value, "/") == 0 && index($value, "//") != 0 && index($value, "\\\\") != 0) : (index($value, "/") == 0 || index($value, "://") >= 0 || index($value, "\\\\") == 0); # TARGET: redirect-absolute-network-path
    }}
    return 0;
}}
1;
'''


def _cpp_policy(family: str, safe: bool) -> str:
    return f'''#include <algorithm>
#include <cctype>
#include <string>

namespace vulnapp {{
const std::string FAMILY = {_quoted(family)};
const bool SAFE = {str(safe).lower()};

static bool starts(const std::string& value, const std::string& prefix) {{ return value.rfind(prefix, 0) == 0; }}
static bool contains(const std::string& value, const std::string& part) {{ return value.find(part) != std::string::npos; }}
static std::string lower(std::string value) {{ for (char& c : value) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c))); return value; }}
static bool number(const std::string& value, long long& result) {{
    try {{ size_t used = 0; result = std::stoll(value, &used); return used == value.size(); }} catch (...) {{ return false; }}
}}

bool allowed(const std::string& value) {{
    if (FAMILY == "path-sibling-prefix")
        return SAFE ? (starts(value, "public/") && !contains(value, "..")) : starts(value, "public"); // TARGET: path-sibling-prefix
    if (FAMILY == "authorization-missing-owner") {{
        const auto split = value.find(':'); if (split == std::string::npos) return false;
        const auto user = value.substr(0, split), owner = value.substr(split + 1);
        return SAFE ? user == owner : !owner.empty(); // TARGET: authorization-missing-owner
    }}
    if (FAMILY == "negative-amount") {{
        long long amount; if (!number(value, amount)) return false;
        return SAFE ? (amount >= 0 && amount <= 100) : amount <= 100; // TARGET: negative-amount
    }}
    if (FAMILY == "integer-boundary") {{
        long long amount; if (!number(value, amount)) return false;
        return SAFE ? (amount >= 0 && amount <= 99) : amount >= 0; // TARGET: integer-boundary
    }}
    if (FAMILY == "url-hostname-suffix") {{
        auto authority = value; const auto scheme = authority.find("://"); if (scheme != std::string::npos) authority = authority.substr(scheme + 3);
        authority = authority.substr(0, authority.find('/')); auto host = authority.substr(authority.rfind('@') == std::string::npos ? 0 : authority.rfind('@') + 1);
        host = host.substr(0, host.find(':'));
        return SAFE ? lower(host) == "api.example.test" : contains(lower(authority), "api.example.test"); // TARGET: url-hostname-suffix
    }}
    if (FAMILY == "command-argument-validation") {{
        const bool valid = !value.empty() && std::all_of(value.begin(), value.end(), [](unsigned char c) {{ return std::isalnum(c) || c == '_'; }});
        return SAFE ? valid : !value.empty(); // TARGET: command-argument-validation
    }}
    if (FAMILY == "object-property-pollution")
        return SAFE ? !(value == "__proto__" || value == "constructor" || value == "prototype" || value == "__defineGetter__" || value == "__defineSetter__") : !value.empty(); // TARGET: object-property-pollution
    if (FAMILY == "header-crlf")
        return SAFE ? (!contains(value, "\\r") && !contains(value, "\\n")) : !value.empty(); // TARGET: header-crlf
    if (FAMILY == "filename-extension-case")
        return SAFE ? (value.size() >= 4 && value.substr(value.size() - 4) == ".pdf") : contains(lower(value), ".pdf"); // TARGET: filename-extension-case
    if (FAMILY == "token-expiry-boundary") {{
        const auto split = value.find('|'); if (split == std::string::npos) return false; long long expiry, now;
        if (!number(value.substr(0, split), expiry) || !number(value.substr(split + 1), now)) return false;
        return SAFE ? expiry > now : expiry >= now; // TARGET: token-expiry-boundary
    }}
    if (FAMILY == "redirect-absolute-network-path")
        return SAFE ? (starts(value, "/") && !starts(value, "//") && !starts(value, "\\\\")) : (starts(value, "/") || contains(value, "://") || starts(value, "\\\\")); // TARGET: redirect-absolute-network-path
    return false;
}}
}} // namespace vulnapp
'''


def _common_files(language: str, family: str, safe: bool, java_build: str | None = None, cpp_build: str | None = None) -> dict[str, str]:
    """Source-tree files for a language/revision; build choice alternates Java/C++ fixtures."""
    if language == "python":
        return {
            "pyproject.toml": '''[build-system]\nrequires = ["setuptools"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "corsair-polyglot-fixture"\nversion = "0.0.0"\nrequires-python = ">=3.10"\n\n[tool.setuptools]\npackages = ["vulnapp"]\n''',
            "vulnapp/__init__.py": "from .policy import allowed\n",
            "vulnapp/policy.py": _python_policy(family, safe),
            "vulnapp/__main__.py": '''import sys\nfrom .policy import allowed\n\nif __name__ == "__main__":\n    print("ALLOW" if len(sys.argv) == 2 and allowed(sys.argv[1]) else "DENY")\n''',
        }
    if language == "javascript":
        return {
            "package.json": json.dumps({"name": "corsair-polyglot-fixture", "private": True, "version": "0.0.0",
                                        "type": "module", "scripts": {"build": "node --check src/policy.js && npm pack --dry-run"}}, indent=2) + "\n",
            "src/policy.js": _js_policy(family, safe, typescript=False),
            "src/cli.js": '''import { allowed } from "./policy.js";\nconst value = process.argv[2];\nconsole.log(value !== undefined && allowed(value) ? "ALLOW" : "DENY");\n''',
        }
    if language == "typescript":
        return {
            "package.json": json.dumps({"name": "corsair-polyglot-fixture", "private": True, "version": "0.0.0",
                                        "type": "module", "devDependencies": {"@types/node": "22.10.7", "typescript": "5.7.3", "vite": "6.0.11"},
                                        "scripts": {"build": "tsc && vite build"}}, indent=2) + "\n",
            "tsconfig.json": '''{"compilerOptions":{"target":"ES2022","module":"ES2022","moduleResolution":"bundler","strict":true,"rootDir":"src","outDir":"dist","sourceMap":true,"types":["node"]},"include":["src"]}
''',
            "vite.config.ts": '''import { defineConfig } from "vite";
export default defineConfig({ build: { outDir: "web-dist" } });
''',
            "index.html": '<div id="app">corsair fixture</div><script type="module" src="/src/main.ts"></script>\n',
            "src/main.ts": '''import { allowed } from "./policy.js";

const app = document.querySelector("#app")!;
app.textContent = allowed("build_probe") ? "corsair fixture: policy loaded" : "corsair fixture: policy loaded";
''',
            "src/policy.ts": _js_policy(family, safe, typescript=True),
            "src/cli.ts": '''import { allowed } from "./policy.js";
const value = process.argv[2];
console.log(value !== undefined && allowed(value) ? "ALLOW" : "DENY");
''',
        }
    if language == "java":
        base = {
            "src/main/java/bench/Policy.java": _java_policy(family, safe),
            "src/main/java/bench/Main.java": '''package bench;\npublic final class Main { public static void main(String[] args) { System.out.println(args.length == 1 && Policy.allowed(args[0]) ? "ALLOW" : "DENY"); } }\n''',
        }
        if java_build == "maven":
            return {"pom.xml": '''<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><groupId>bench</groupId><artifactId>fixture</artifactId><version>0.0.0</version><properties><maven.compiler.source>17</maven.compiler.source><maven.compiler.target>17</maven.compiler.target><maven.compiler.release>17</maven.compiler.release></properties></project>\n''', **base}
        return {"settings.gradle": "rootProject.name = 'fixture'\n", "build.gradle": "plugins { id 'java' }\nsourceCompatibility = JavaVersion.VERSION_17\ntargetCompatibility = JavaVersion.VERSION_17\n", **base}
    if language == "ruby":
        return {
            "Gemfile": '''source "https://rubygems.org"\ngem "rake", "~> 13.0"\n''',
            "Rakefile": '''require "rake"\ntask :build do\n  sh "ruby -c lib/vulnapp.rb"\nend\n''',
            "lib/vulnapp.rb": _ruby_policy(family, safe),
            "script/validate.rb": '''require_relative "../lib/vulnapp"\nvalue = ARGV[0]\nputs(value && VulnApp.allowed(value) ? "ALLOW" : "DENY")\n''',
        }
    if language == "perl":
        return {
            "Makefile.PL": '''use ExtUtils::MakeMaker;\nWriteMakefile(NAME => "VulnApp", VERSION => "0.01");\n''',
            "lib/VulnApp.pm": _perl_policy(family, safe),
            "script/validate.pl": '''#!/usr/bin/env perl\nuse strict; use warnings; use lib "lib"; use VulnApp;\nmy $value = $ARGV[0];\nprint defined($value) && VulnApp::allowed($value) ? "ALLOW\\n" : "DENY\\n";\n''',
            "t/policy.t": f'''use strict; use warnings; use Test::More tests => 1; use lib "lib"; use VulnApp; ok(VulnApp::allowed({_quoted(FAMILY_BY_SLUG[family].control)}), "module loads and evaluates the family control");\n''',
        }
    if language == "cpp":
        base = {
            "src/policy.cpp": _cpp_policy(family, safe),
            "src/main.cpp": '''#include <iostream>\n#include <string>\nnamespace vulnapp { bool allowed(const std::string&); }\nint main(int argc, char** argv) { std::cout << (argc == 2 && vulnapp::allowed(argv[1]) ? "ALLOW" : "DENY") << "\\n"; }\n''',
        }
        if cpp_build == "cmake":
            return {"CMakeLists.txt": '''cmake_minimum_required(VERSION 3.16)\nproject(corsair_fixture LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 17)\nset(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} --coverage -O0 -g")\nadd_executable(vulnapp src/main.cpp src/policy.cpp)\n''', **base}
        return {"Makefile": '''CXX ?= g++\nCXXFLAGS = -std=c++17 --coverage -O0 -g -Wall -Wextra\nall: vulnapp\nvulnapp: src/main.cpp src/policy.cpp\n\t$(CXX) $(CXXFLAGS) -o $@ src/main.cpp src/policy.cpp\nclean:\n\trm -f vulnapp\n''', **base}
    raise ValueError(f"unsupported language: {language}")


def _build_spec(language: str, variant: int) -> tuple[str, tuple[str, ...], str | None, str | None]:
    """The exact build command and post-build command.  Java/C++ alternate frameworks."""
    if language == "python":
        return "python -c \"import setuptools; print(setuptools.__version__)\" && python -m pip install --no-build-isolation --no-deps . && python -m compileall -q vulnapp", ("python", "-m", "vulnapp"), None, None
    if language == "javascript":
        return "npm run build", ("node", "src/cli.js"), None, None
    if language == "typescript":
        return "npm install --ignore-scripts --no-audit --no-fund && npm run build", ("node", "dist/cli.js"), None, None
    if language == "java":
        if variant % 2:
            return "mvn -q -DskipTests package", ("java", "-cp", "target/classes", "bench.Main"), "maven", None
        return "gradle --no-daemon classes", ("java", "-cp", "build/classes/java/main", "bench.Main"), "gradle", None
    if language == "ruby":
        return "bundle install --local --quiet && bundle exec rake build", ("bundle", "exec", "ruby", "script/validate.rb"), None, None
    if language == "perl":
        return "perl Makefile.PL >/dev/null && make >/dev/null && prove -l", ("perl", "-Ilib", "script/validate.pl"), None, None
    if language == "cpp":
        if variant % 2:
            return "cmake -S . -B build >/dev/null && cmake --build build >/dev/null", ("./build/vulnapp",), None, "cmake"
        return "make all", ("./vulnapp",), None, "make"
    raise ValueError(language)


def _probe_predicate(family: str) -> str:
    """Return a pure fixed-policy invariant over one raw payload value."""
    predicates = {
        "path-sibling-prefix": """    return value.startswith(\"public/\") and \"..\" not in value\n""",
        "authorization-missing-owner": """    parts = value.split(\":\", 1)\n    return len(parts) == 2 and parts[0] == parts[1]\n""",
        "negative-amount": """    try:\n        amount = int(value)\n    except ValueError:\n        return False\n    return 0 <= amount <= 100\n""",
        "integer-boundary": """    try:\n        amount = int(value)\n    except ValueError:\n        return False\n    return 0 <= amount <= 99\n""",
        "url-hostname-suffix": """    try:\n        return urllib.parse.urlparse(value).hostname == \"api.example.test\"\n    except ValueError:\n        return False\n""",
        "command-argument-validation": """    return re.fullmatch(r\"[A-Za-z0-9_]+\", value) is not None\n""",
        "object-property-pollution": """    return value not in {\"__proto__\", \"constructor\", \"prototype\", \"__defineGetter__\", \"__defineSetter__\"}\n""",
        "header-crlf": """    return \"\\r\" not in value and \"\\n\" not in value\n""",
        "filename-extension-case": """    return value.endswith(\".pdf\")\n""",
        "token-expiry-boundary": """    try:\n        expiry_text, now_text = value.split(\"|\", 1)\n        expiry, now = int(expiry_text), int(now_text)\n    except ValueError:\n        return False\n    return expiry > now\n""",
        "redirect-absolute-network-path": """    return value.startswith(\"/\") and not value.startswith(\"//\") and not value.startswith(\"\\\\\")\n""",
    }
    try:
        return predicates[family]
    except KeyError as error:
        raise ValueError(f"unsupported family: {family}") from error


def _probe(language: str, family: str, command: tuple[str, ...], control: str, exploit: str) -> str:
    """One differential probe with an independently rendered invariant for both raw strings."""
    if language == "python":
        invocation = """from vulnapp.policy import allowed


def run_target(payload: str) -> None:
    decision = \"ALLOW\" if allowed(payload) else \"DENY\"
    assert decision != \"ALLOW\" or safe_predicate(payload), \"target accepted a value outside the independently derived security invariant\"
"""
    else:
        invocation = f"""import subprocess


COMMAND = {_json_list(command)}


def run_target(payload: str) -> None:
    completed = subprocess.run([*COMMAND, payload], text=True, capture_output=True, check=False, timeout=20)
    if completed.returncode != 0:
        raise RuntimeError(f\"target exited {{completed.returncode}}: {{completed.stderr[-500:]}}\")
    decision = completed.stdout.strip()
    if decision not in {{\"ALLOW\", \"DENY\"}}:
        raise RuntimeError(f\"unexpected policy response: {{decision!r}}\")
    assert decision != \"ALLOW\" or safe_predicate(payload), \"target accepted a value outside the independently derived security invariant\"
"""
    return f"""import re
import urllib.parse


CONTROL_PAYLOAD = {_quoted(control)}
EXPLOIT_PAYLOAD = {_quoted(exploit)}


def safe_predicate(value: str) -> bool:
{_probe_predicate(family)}
{invocation}"""


def _json_list(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _target_line(path: Path, family: str) -> int:
    needle = f"TARGET: {family}"
    matches = [number for number, line in enumerate(path.read_text().splitlines(), 1) if needle in line]
    if len(matches) != 1:
        raise ValueError(f"{path}: expected one {needle!r}, found {matches}")
    return matches[0]


def _target_file(language: str) -> str:
    return {
        "python": "vulnapp/policy.py", "javascript": "src/policy.js", "typescript": "src/policy.ts",
        "java": "src/main/java/bench/Policy.java", "ruby": "lib/vulnapp.rb", "perl": "lib/VulnApp.pm", "cpp": "src/policy.cpp",
    }[language]


def _target_symbol(language: str) -> str:
    return {"python": "allowed", "javascript": "allowed", "typescript": "allowed", "java": "allowed", "ruby": "allowed", "perl": "allowed", "cpp": "allowed"}[language]


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _write_case(root: Path, language: str, family: Family, variant: int) -> Path:
    directory = root / language / f"{family.slug}-v{variant}"
    vulnerable, fixed = directory / "vulnerable", directory / "fixed"
    build, command, java_build, cpp_build = _build_spec(language, variant)
    _write_tree(vulnerable, _common_files(language, family.slug, False, java_build, cpp_build))
    _write_tree(fixed, _common_files(language, family.slug, True, java_build, cpp_build))
    target_file = _target_file(language)
    line = _target_line(vulnerable / target_file, family.slug)
    if _target_line(fixed / target_file, family.slug) != line:
        raise ValueError(f"target line drift between revisions for {directory}")
    case_id = f"polyglot/{language}/{family.slug}/v{variant}"
    finding = {"title": family.title, "description": family.root_cause, "file_path": target_file,
               "start_line": line, "symbol": _target_symbol(language), "cwe": family.cwe}
    input_data = {"case_id": case_id, "finding": finding, "source": "vulnerable", "fixed_source": "fixed"}
    hypothesis = Hypothesis(target_file=target_file, target_symbol=_target_symbol(language), target_lines=(line,),
                            root_cause=family.root_cause, expected_violation=family.expected_violation)
    submission = Submission(hypothesis=hypothesis, build_script=build, probe=_probe(language, family.slug, command, family.control, family.exploits[variant - 1]))
    provenance = {"schema": "corsair-polyglot/provenance/1", "generator": GENERATOR_VERSION, "case_id": case_id,
                  "language": language, "family": family.slug, "variant": variant, "counting_unit": "twin-revision",
                  "runnable_revision_variants": 2, "control": family.control, "exploit": family.exploits[variant - 1],
                  "command": list(command), "build_command": build, "target_file": target_file, "target_line": line}
    oracle = {"schema": "corsair-polyglot/oracle/1", "expected_label": "LIKELY_EXPLOITABLE", "expected_fix": "verified",
              "acceptable_labels": ["LIKELY_EXPLOITABLE"], "provenance": {"generator": GENERATOR_VERSION,
              "language": language, "family": family.slug, "variant": variant}}
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "input.json").write_text(json.dumps(input_data, indent=2) + "\n")
    (directory / "reference-submission.json").write_text(submission.model_dump_json(indent=2) + "\n")
    (directory / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    # Evaluator-only: neither input.json nor Submission contains the expected label.
    (directory / "oracle.json").write_text(json.dumps(oracle, indent=2) + "\n")
    return directory


def generate(root: Path | str, languages: Iterable[str] | None = None) -> list[Path]:
    """Generate deterministic case directories under *root* and return them in stable order.

    ``languages`` is an optional iterable of the lowercase names in :data:`LANGUAGES`.
    Existing matching case files are overwritten deterministically; unrelated files are
    not removed.  The returned paths are case directories suitable for ``load_case``.
    """
    root = Path(root).resolve()
    requested = LANGUAGES if languages is None else tuple(dict.fromkeys(languages))
    unknown = sorted(set(requested) - set(LANGUAGES))
    if unknown:
        raise ValueError(f"unsupported language(s): {', '.join(unknown)}")
    root.mkdir(parents=True, exist_ok=True)
    paths = [_write_case(root, language, family, variant)
             for language in requested for family in FAMILIES for variant in range(1, 6)]
    catalog = {"schema": "corsair-polyglot/catalog/1", "generator": GENERATOR_VERSION, "languages": list(requested),
               "families": [family.slug for family in FAMILIES], "case_directories": len(paths),
               "runnable_revision_variants": len(paths) * 2,
               "per_language_runnable_revision_variants": len(FAMILIES) * 5 * 2,
               "note": "Twin revisions are counted as runnable revision-variants, not as distinct CVEs."}
    (root / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    return paths
