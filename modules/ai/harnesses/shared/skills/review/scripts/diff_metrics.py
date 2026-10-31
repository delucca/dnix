#!/usr/bin/env python3
"""diff-metrics: deterministic, read-only measurements of a diff for the review gate."""
import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time

SCHEMA = 1

GIT_C = [
    "-c", "core.quotePath=true", "-c", "core.fsmonitor=false",
    "-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false",
    "-c", "diff.relative=false", "-c", "color.ui=never",
    "-c", "log.showSignature=false",
]
DIFF_FLAGS = ["--no-ext-diff", "--no-textconv", "--no-color", "-M", "--diff-algorithm=myers", "-U3"]
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

LOCK_FILES = {
    "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "go.sum",
    "Cargo.lock", "flake.lock", "poetry.lock", "uv.lock", "Gemfile.lock", "composer.lock",
    "Podfile.lock", "Package.resolved",
}
EXCLUDED_SEGMENTS = ("vendor", "node_modules", "dist", "third_party")
EXCLUDED_SUFFIXES = (
    ".pb.go", "_pb2.py", "_pb2_grpc.py", ".min.js", ".min.css", ".g.dart", ".freezed.dart",
)
GENERATED_RE = re.compile(r"@generated|Code generated .* DO NOT EDIT|DO NOT EDIT|auto-?generated", re.I)

EXT_LANG = {
    "py": "python", "pyi": "python", "js": "javascript", "jsx": "javascript", "mjs": "javascript",
    "cjs": "javascript", "ts": "typescript", "tsx": "typescript", "mts": "typescript",
    "cts": "typescript", "go": "go", "rs": "rust", "java": "java", "kt": "kotlin", "kts": "kotlin",
    "swift": "swift", "m": "objc", "mm": "objc", "c": "c", "h": "c", "cc": "cpp", "cpp": "cpp",
    "hpp": "cpp", "cs": "csharp", "rb": "ruby", "php": "php", "scala": "scala", "dart": "dart",
    "lua": "lua", "sh": "shell", "bash": "shell", "zsh": "shell", "nix": "nix", "el": "elisp",
    "clj": "clojure", "cljs": "clojure", "edn": "clojure", "rkt": "racket", "scm": "scheme",
    "lisp": "lisp", "hs": "haskell", "ml": "ocaml", "ex": "elixir", "exs": "elixir",
    "erl": "erlang", "sql": "sql", "md": "markdown", "yaml": "yaml", "yml": "yaml",
    "toml": "toml", "json": "json", "vue": "vue", "svelte": "svelte", "tex": "tex", "r": "r",
}
NAME_LANG = {"Makefile": "make", "justfile": "just", "Dockerfile": "docker"}
DOC_LANGS = {"markdown", "json", "yaml", "toml", "tex"}
NO_COVERAGE_LANGS = {"nix", "make", "just", "docker", "sql", "shell", "markdown", "yaml", "toml", "json", "tex"}
PLAIN_EXTS = {"txt", "csv", "tsv", "svg", "gitignore", "lock"}

HASH_LANGS = {"python", "shell", "ruby", "nix", "yaml", "toml", "r", "make", "docker", "just", "elixir"}
SLASH_LANGS = {
    "c", "cpp", "objc", "javascript", "typescript", "go", "rust", "java", "kotlin", "swift",
    "scala", "csharp", "dart", "php", "vue", "svelte",
}
COMMENT_MARKERS = {}
for _l in HASH_LANGS:
    COMMENT_MARKERS[_l] = ("#",)
for _l in SLASH_LANGS:
    COMMENT_MARKERS[_l] = ("//", "/*", "*", "*/")
for _l in ("sql", "lua", "haskell"):
    COMMENT_MARKERS[_l] = ("--",)
for _l in ("elisp", "clojure", "racket", "scheme", "lisp"):
    COMMENT_MARKERS[_l] = (";",)
for _l in ("erlang", "tex"):
    COMMENT_MARKERS[_l] = ("%",)
LINE_MARKERS = {"#", "//", "--", ";", "%"}

TEST_PATH_RES = [re.compile(p) for p in (
    r"(^|/)(test|tests|spec|specs|__tests__)/", r"_test\.(go|py|rb|exs)$", r"(^|/)test_[^/]*\.py$",
    r"\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs|mts|cts)$", r"Tests?\.(swift|kt|java|cs)$",
    r"_spec\.rb$", r"-tests?\.el$",
)]

DEF_GROUP = {
    "python": "python", "go": "go", "rust": "rust", "javascript": "js", "typescript": "js",
    "vue": "js", "svelte": "js", "java": "java", "kotlin": "kotlin", "swift": "swift",
    "ruby": "ruby", "elisp": "elisp", "clojure": "clojure",
}
RUST_FN = r"(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)"
DEFS = {
    "python": ("one", re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)")),
    "go": ("one", re.compile(r"^func\s+((?:Test|Benchmark|Fuzz)\w*)\s*\(")),
    "rust": ("two", re.compile(r"#\[(?:tokio::|async_std::)?test\]"), re.compile(RUST_FN)),
    "js": ("one", re.compile(r"^\s*(?:it|test)(?:\.\w+)?\s*\(\s*(['\"\x60])(.+?)\1")),
    "java": ("two", re.compile(r"^\s*@Test\b"), re.compile(r"void\s+(\w+)\s*\(")),
    "kotlin": ("two", re.compile(r"^\s*@Test\b"),
               re.compile(r"(?:suspend\s+)?fun\s+(?:\x60([^\x60]+)\x60|(\w+))")),
    "swift": ("one", re.compile(r"func\s+(test\w+)\s*\(")),
    "ruby": ("one", re.compile(r"^\s*it\s+['\"](.+?)['\"]")),
    "elisp": ("one", re.compile(r"\(ert-deftest\s+([\w-]+)")),
    "clojure": ("one", re.compile(r"\(deftest\s+([\w-]+)")),
}

SKIP_RES = [re.compile(p) for p in (
    r"@pytest\.mark\.(?:skip|skipif|xfail)", r"@unittest\.skip", r"pytest\.skip\(",
    r"\b(?:it|test|describe)\.(?:skip|todo)\(", r"\bxit\(", r"\bxtest\(", r"\bxdescribe\(",
    r"\.only\(", r"\bfit\(", r"\bfdescribe\(", r"\bt\.(?:Skip|Skipf|SkipNow)\(", r"#\[ignore\b",
    r"@Ignore\b", r"@Disabled\b", r"XCTSkip", r"\(skip-unless",
)]
RUBY_SKIP_RE = re.compile(r"^\s*(?:skip|pending|xit)\b")
SKIP_LANGS = set(DEF_GROUP) | {"csharp", "scala", "php", "c", "cpp", "objc"}

ASSERT_RE = re.compile("|".join((
    r"\bassert", r"assert_eq!", r"assert_ne!", r"assert!", r"debug_assert", r"expect\(",
    r"\.should\b", r"\bshould\b", r"t\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow)\b",
    r"\brequire\.\w+\(", r"\bassert\.\w+\(", r"XCTAssert", r"#expect\(", r"#require\(",
    r"self\.assert", r"assertThat", r"pytest\.raises", r"verify\(", r"\(should\b", r"\(is\s",
    r"EXPECT_", r"ASSERT_", r"toMatchSnapshot", r"toMatchInlineSnapshot",
)))
TRIVIAL_RE = re.compile("|".join((
    r"^\s*assert\s+(?:True|1)\s*(?:,.*)?$", r"assert!\(\s*true\s*\)", r"expect\(\s*true\s*\)\.toBe\(\s*true\s*\)",
    r"XCTAssertTrue\(\s*true\s*\)",
)))

SUPPRESS = [
    ({"py", "pyi"}, ("# noqa", "# type: ignore", "# pyright: ignore", "# pylint: disable",
                     "# pragma: no cover", "# nosec", "# mypy: ignore-errors", "# ruff: noqa")),
    ({"js", "jsx", "mjs", "cjs", "ts", "tsx", "mts", "cts", "vue", "svelte"},
     ("eslint-disable", "@ts-ignore", "@ts-expect-error", "@ts-nocheck", "istanbul ignore",
      "c8 ignore", "v8 ignore", "biome-ignore", "oxlint-disable")),
    ({"go"}, ("//nolint", "// nolint", "#nosec", "//lint:ignore")),
    ({"rs"}, ("#[allow(", "#![allow(", "#[expect(", "#[coverage(off)]", "tarpaulin_include")),
    ({"java", "kt", "kts"}, ("@SuppressWarnings", "@Suppress(", "//noinspection", "NOSONAR")),
    ({"swift"}, ("swiftlint:disable",)),
    ({"rb"}, ("rubocop:disable", ":nocov:")),
    ({"sh", "bash", "zsh"}, ("shellcheck disable=",)),
    ({"c", "h", "cc", "cpp", "hpp", "m", "mm"},
     ("NOLINT", "LCOV_EXCL", "#pragma warning(disable", "#pragma GCC diagnostic ignored")),
    ({"cs"}, ("#pragma warning disable", "[SuppressMessage(", "[ExcludeFromCodeCoverage")),
]
DIRECTIVE_RE = re.compile(
    r"eslint-|prettier-ignore|noqa|type:\s*ignore|\bgo:|\+build|nolint|shellcheck|pragma|"
    r"pyright:|pylint:|mypy:|ruff:|istanbul|c8 ignore|v8 ignore|biome-ignore|rubocop:|swiftlint:|NOSONAR|NOLINT"
)

GATE_PATTERNS = (
    ".eslintrc*", "eslint.config.*", "tsconfig*.json", "pyproject.toml", "setup.cfg", "tox.ini",
    ".flake8", "ruff.toml", ".ruff.toml", "mypy.ini", ".pylintrc", "pylintrc", ".coveragerc",
    ".golangci.y*ml", "clippy.toml", ".clippy.toml", "Cargo.toml", "jest.config.*",
    "vitest.config.*", ".nycrc*", ".c8rc*", "codecov.y*ml", ".codecov.y*ml",
    "sonar-project.properties", ".pre-commit-config.yaml", ".github/workflows/*.y*ml",
    ".gitlab-ci.yml", ".buildkite/*", "Jenkinsfile", ".circleci/config.yml", "Makefile",
    "justfile", ".husky/*", "lefthook.y*ml", ".swiftlint.yml", "detekt.yml",
)
CI_PATTERNS = (
    ".github/workflows/*.y*ml", ".gitlab-ci.yml", ".buildkite/*", "Jenkinsfile",
    ".circleci/config.yml", ".husky/*", "lefthook.y*ml", ".pre-commit-config.yaml",
)
GATE_ADD_RES = [re.compile(p) for p in (
    r"continue-on-error:\s*true", r"allow_failure:\s*true", r"soft_fail", r"\|\|\s*true",
    r"--no-verify", r"ignore\s*=", r"extend-ignore", r"per-file-ignores", r"disable\s*=",
    r"disable_error_code", r"ignore_errors\s*=\s*true", r"ignore_missing_imports",
    r"\"strict\":\s*false", r"\"noImplicitAny\":\s*false", r"\"skipLibCheck\":\s*true",
    r"omit\s*=", r"exclude\s*=", r"--ignore", r"--deselect", r"= \"allow\"",
)]
ESLINT_OFF_RE = re.compile(r":\s*[\"']?off[\"']?|:\s*0\b")
KEY_NUM_RE = re.compile(r"^\s*[\"']?([\w.\-]+)[\"']?\s*[:=]\s*[\"']?(\d+(?:\.\d+)?)")
LOWER_KEY_RE = re.compile(r"threshold|fail_under|fail-under|minimum|min_|coverage|branches|lines|functions|statements", re.I)
UPPER_KEY_RE = re.compile(r"^max[-_]\w+", re.I)
CI_RUN_RE = re.compile(r"\b(?:lint|test|check|mypy|clippy|eslint|ruff|pytest|vet)\b")

SEVERITY = {
    "test-deleted": "major", "test-skipped": "major", "assertion-lost": "major",
    "test-no-assertion": "major", "gate-loosened": "major", "suppression": "minor",
}

CODE_COMMENT_RE = re.compile(
    r"^(?:if|for|while|return|def|class|function|const|let|var|import|from|fn|func|pub|print|"
    r"console\.|self\.|this\.)\b"
)
TRIVIAL_IMPORT_RE = re.compile(r"^(?:import\b|from\s+\S+\s+import\b|#include\b|use\s|require\(|package\s)")
NAME_SPLIT_RE = re.compile(r"[\[<=>~!;@ ]")

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
LINT_LOC_RE = re.compile(r"^(.+?):(\d+)(?::\d+)?(?::|\s)")
ESCAPES = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11, "\\": 92, '"': 34}


class Usage(Exception):
    pass


def die(msg):
    sys.stderr.write("diff-metrics: %s\n" % msg)
    sys.exit(2)


def git_env(extra=None):
    env = dict(os.environ)
    for name in ("GIT_EXTERNAL_DIFF", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(name, None)
    env.update(GIT_OPTIONAL_LOCKS="0", LC_ALL="C", GIT_PAGER="cat")
    if extra:
        env.update(extra)
    return env


def git(repo, *args, env=None, stdin=None):
    """Runs git with every output knob pinned; returns the CompletedProcess with bytes."""
    return subprocess.run(
        ["git"] + GIT_C + list(args), cwd=repo, env=git_env(env), input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def git_ok(repo, *args, ok=(0,), env=None):
    """stdout of a git call whose exit code is in OK; any other exit is an error, never an empty result."""
    p = git(repo, *args, env=env)
    if p.returncode not in ok:
        die("git %s failed (exit %d): %s" % (args[0], p.returncode,
                                             p.stderr.decode("utf-8", "replace").strip().split("\n")[-1]))
    return p.stdout


def git_out(repo, *args, env=None):
    p = git(repo, *args, env=env)
    return p.stdout.decode("utf-8", "replace").strip() if p.returncode == 0 else None


def toplevel(path):
    try:
        p = git(path, "rev-parse", "--show-toplevel")
    except OSError:
        return None
    return p.stdout.decode("utf-8", "replace").strip() if p.returncode == 0 else None


def resolve_repo(arg):
    top = toplevel(arg or os.getcwd())
    if arg and not top:
        die("not a git repository: %s" % arg)
    return top


def base_exists(repo, rev):
    return git(repo, "cat-file", "-e", rev + "^{tree}").returncode == 0


def resolve_rev(repo, rev):
    """Commit SHA when REV is a commit, else its tree id, else None."""
    out = git_out(repo, "rev-parse", "--verify", "--quiet", rev + "^{commit}")
    if out:
        return out
    return git_out(repo, "rev-parse", "--verify", "--quiet", rev + "^{tree}")


def build_diff(repo, base, mode, head_rev=None, binary=False):
    if not base_exists(repo, base):
        die("base does not resolve: %s" % base)
    flags = DIFF_FLAGS + (["--binary", "--full-index"] if binary else [])
    if mode == "head":
        if not base_exists(repo, head_rev):
            die("head does not resolve: %s" % head_rev)
        parts = [git_ok(repo, "diff", *flags, base, head_rev)]
    elif mode == "index":
        parts = [git_ok(repo, "diff", "--cached", *flags, base)]
    else:
        parts = [git_ok(repo, "diff", *flags, base)]
        raw = git_ok(repo, "ls-files", "--others", "--exclude-standard", "-z")
        for name in sorted(n for n in raw.split(b"\0") if n and not n.endswith(b"/")):
            parts.append(git_ok(repo, "diff", "--no-index", *flags, "--", "/dev/null",
                                name.decode("utf-8", "surrogateescape"), ok=(0, 1)))
    return b"".join(parts)


def cmd_diff(args):
    repo = resolve_repo(args.repo)
    if not repo:
        die("not a git repository")
    if args.head:
        data = build_diff(repo, args.base, "head", args.head, args.binary)
    elif args.index:
        data = build_diff(repo, args.base, "index", binary=args.binary)
    else:
        data = build_diff(repo, args.base, "worktree", binary=args.binary)
    sys.stdout.buffer.write(data)
    return 0


class Hunk(object):
    def __init__(self, old_start, old_len, new_start, new_len):
        self.old_start, self.old_len, self.new_start, self.new_len = old_start, old_len, new_start, new_len
        self.lines = []


class DFile(object):
    def __init__(self):
        self.path = None
        self.old_path = None
        self.status = "modified"
        self.binary = False
        self.hunks = []
        self.added = 0
        self.deleted = 0
        self.rename = False


def unquote(token):
    body = token[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            n = body[i + 1]
            if n in "01234567":
                j = i + 1
                while j < len(body) and j < i + 4 and body[j] in "01234567":
                    j += 1
                out.append(int(body[i + 1:j], 8) & 255)
                i = j
                continue
            if n in ESCAPES:
                out.append(ESCAPES[n])
                i += 2
                continue
        out += c.encode("utf-8", "replace")
        i += 1
    return out.decode("utf-8", "replace")


def quoted_end(s):
    i = 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == '"':
            return i
        i += 1
    return len(s) - 1


def path_token(s, prefix=True):
    s = s.rstrip("\t")
    if s == "/dev/null":
        return None
    p = unquote(s) if s.startswith('"') else s
    return p[2:] if prefix and p[:2] in ("a/", "b/") else p


def split_git_header(rest):
    """Best-effort paths of a 'diff --git' line; later header lines override."""
    if rest.startswith('"'):
        end = quoted_end(rest)
        a = path_token(rest[:end + 1])
        b = path_token(rest[end + 1:].strip())
        return a, b
    if ' "b/' in rest:
        k = rest.index(' "b/')
        return path_token(rest[:k]), path_token(rest[k + 1:])
    pos = 0
    while True:
        k = rest.find(" b/", pos)
        if k < 0:
            break
        if rest[2:k] == rest[k + 3:]:
            return rest[2:k], rest[k + 3:]
        pos = k + 1
    k = rest.find(" b/")
    if k > 0:
        return rest[2:k], rest[k + 3:]
    return rest, rest


def unsafe_path(name):
    return name.startswith("/") or ".." in name.split("/") or "\0" in name


def parse_diff(data):
    lines = data.decode("utf-8", "replace").split("\n")
    files = []
    cur = None
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("diff --git "):
            cur = DFile()
            a, b = split_git_header(line[len("diff --git "):])
            cur.path = b if b is not None else a
            cur.old_path = a
            files.append(cur)
        elif cur is not None:
            if line.startswith("new file mode"):
                cur.status = "added"
            elif line.startswith("deleted file mode"):
                cur.status = "deleted"
            elif line.startswith("rename from "):
                cur.status = "renamed"
                cur.rename = True
                cur.old_path = path_token(line[len("rename from "):], prefix=False)
            elif line.startswith("rename to "):
                cur.path = path_token(line[len("rename to "):], prefix=False)
            elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
                cur.binary = True
            elif line.startswith("--- ") and not cur.hunks:
                a = path_token(line[4:])
                if a is not None:
                    cur.old_path = a
                else:
                    cur.status = "added"
            elif line.startswith("+++ ") and not cur.hunks:
                b = path_token(line[4:])
                if b is not None:
                    cur.path = b
                else:
                    cur.status = "deleted"
                    cur.path = cur.old_path
            elif line.startswith("@@"):
                m = HUNK_RE.match(line)
                if m:
                    ol = int(m.group(2)) if m.group(2) is not None else 1
                    nl = int(m.group(4)) if m.group(4) is not None else 1
                    h = Hunk(int(m.group(1)), ol, int(m.group(3)), nl)
                    old_no, new_no = h.old_start, h.new_start
                    ro, rn = ol, nl
                    while (ro > 0 or rn > 0) and i + 1 < n:
                        i += 1
                        t = lines[i]
                        c = t[:1]
                        if c == "\\":
                            continue
                        if c == "-":
                            h.lines.append(("-", t[1:], old_no, None))
                            old_no += 1
                            ro -= 1
                            cur.deleted += 1
                        elif c == "+":
                            h.lines.append(("+", t[1:], None, new_no))
                            new_no += 1
                            rn -= 1
                            cur.added += 1
                        else:
                            h.lines.append((" ", t[1:], old_no, new_no))
                            old_no += 1
                            new_no += 1
                            ro -= 1
                            rn -= 1
                    cur.hunks.append(h)
        i += 1
    for f in files:
        if f.status == "renamed" and f.old_path == f.path:
            f.status = "modified"
        for name in (f.path, f.old_path):
            if name and unsafe_path(name):
                die("the diff names a path outside the repository: %s" % name)
    return files


def read_blobs(repo, specs):
    """spec ('REV:PATH' or ':PATH') -> bytes or None, one cat-file process."""
    specs = [s for s in specs if "\n" not in s]
    if not specs:
        return {}
    inp = ("\n".join(specs) + "\n").encode("utf-8", "surrogateescape")
    p = git(repo, "cat-file", "--batch", stdin=inp)
    out = p.stdout
    res = {}
    pos = 0
    for s in specs:
        nl = out.find(b"\n", pos)
        if nl < 0:
            res[s] = None
            continue
        header = out[pos:nl]
        pos = nl + 1
        parts = header.split(b" ")
        if header.endswith(b" missing") or len(parts) != 3 or parts[1] != b"blob":
            res[s] = None
            if len(parts) == 3 and parts[2].isdigit():
                pos += int(parts[2]) + 1
            continue
        size = int(parts[2])
        res[s] = out[pos:pos + size]
        pos += size + 1
    return res


def as_text(b):
    if b is None or b"\0" in b[:8000]:
        return None
    return b.decode("utf-8", "replace")


class Contents(object):
    def __init__(self, repo, base, head):
        self.repo, self.base_rev, self.head_rev = repo, base, head
        self.cache = {}

    def _blob(self, spec):
        if spec not in self.cache:
            if "\n" in spec:
                p = git(self.repo, "show", spec)
                self.cache[spec] = p.stdout if p.returncode == 0 else None
            else:
                self.cache[spec] = read_blobs(self.repo, [spec]).get(spec)
        return self.cache[spec]

    def can_head(self):
        return bool(self.repo and self.head_rev)

    def can_base(self):
        return bool(self.repo and self.base_rev)

    def head(self, path):
        if not self.can_head():
            return None
        if self.head_rev == "worktree":
            full = os.path.join(self.repo, path)
            if unsafe_path(path) or os.path.islink(full) or not os.path.isfile(full):
                return None
            with open(full, "rb") as fh:
                return as_text(fh.read())
        spec = (":" + path) if self.head_rev == "index" else "%s:%s" % (self.head_rev, path)
        return as_text(self._blob(spec))

    def base(self, path):
        if not self.can_base():
            return None
        return as_text(self._blob("%s:%s" % (self.base_rev, path)))


def lang_of(path):
    base = os.path.basename(path)
    if base in NAME_LANG:
        return NAME_LANG[base]
    ext = base.rsplit(".", 1)[1].lower() if "." in base else ""
    return EXT_LANG.get(ext)


def ext_of(path):
    base = os.path.basename(path)
    return base.rsplit(".", 1)[1].lower() if "." in base else ""


def is_test_path(path):
    return any(r.search(path) for r in TEST_PATH_RES)


def excluded_path(path):
    base = os.path.basename(path)
    if base in LOCK_FILES or base.endswith(".lock"):
        return True
    if any(seg in EXCLUDED_SEGMENTS for seg in path.split("/")[:-1]):
        return True
    if path.endswith(EXCLUDED_SUFFIXES) or re.search(r"\.generated\.", base):
        return True
    return False


def head_first_lines(f, contents):
    text = contents.head(f.path) if contents else None
    if text is not None:
        return text.split("\n")[:5]
    for h in f.hunks:
        if h.new_start == 1:
            return [t for tag, t, _, _ in h.lines if tag in "+ "][:5]
    return []


def is_excluded(f, contents):
    if excluded_path(f.path):
        return True
    if f.binary or f.status == "deleted" or is_test_path(f.path) or matches_any(f.path, GATE_PATTERNS):
        return False
    if not any(GENERATED_RE.search(l) for l in head_first_lines(f, contents)):
        return False
    if f.status == "added" or not (contents and contents.can_base()):
        return True
    base = contents.base(f.old_path or f.path)
    return base is None or any(GENERATED_RE.search(l) for l in base.split("\n")[:5])


def merge_ranges(nums):
    out = []
    for n in sorted(nums):
        if out and n <= out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def find_defs(texts, group):
    """(start_index, name, name_index) for each test definition in TEXTS."""
    spec = DEFS.get(group)
    out = []
    if not spec:
        return out
    if spec[0] == "one":
        for i, t in enumerate(texts):
            m = spec[1].search(t)
            if m:
                name = [g for g in m.groups() if g is not None]
                out.append((i, name[-1] if name else t.strip(), i))
        return out
    for i, t in enumerate(texts):
        if spec[1].search(t):
            for j in range(i, min(i + 4, len(texts))):
                m = spec[2].search(texts[j])
                if m:
                    name = [g for g in m.groups() if g is not None]
                    out.append((i, name[-1], j))
                    break
    return out


def hunk_def_marks(f, group):
    """Per hunk: (removed defs, added defs) as (name, hunk, line index in seq, no)."""
    removed, added = [], []
    for h in f.hunks:
        old = [l for l in h.lines if l[0] in " -"]
        new = [l for l in h.lines if l[0] in " +"]
        for start, name, nidx in find_defs([l[1] for l in old], group):
            if old[start][0] == "-":
                removed.append((name, h, old[start][2], old[start][1], old[nidx][2]))
        for start, name, nidx in find_defs([l[1] for l in new], group):
            if new[start][0] == "+":
                added.append((name, h, new[start][3], new[start][1], new[nidx][3]))
    return removed, added


def analyze_files(files, contents):
    for f in files:
        f.language = lang_of(f.path)
        f.test = is_test_path(f.path)
        f.excluded = is_excluded(f, contents)
        f.group = DEF_GROUP.get(f.language)
        f.removed_defs, f.added_defs = hunk_def_marks(f, f.group) if f.group and not f.binary else ([], [])
    return files


def f_added_lines(f):
    return [(l[3], l[1]) for h in f.hunks for l in h.lines if l[0] == "+"]


def f_removed_lines(f):
    return [(l[2], l[1], h) for h in f.hunks for l in h.lines if l[0] == "-"]


def build_facts(files):
    live = [f for f in files if not f.excluded and not f.binary]
    facts = {
        "S": sum(f.added + f.deleted for f in live),
        "F": sum(1 for f in files if not f.excluded),
        "added": sum(f.added for f in files if not f.excluded),
        "deleted": sum(f.deleted for f in files if not f.excluded),
        "excluded": sorted(f.path for f in files if f.excluded),
        "binary": sorted(f.path for f in files if f.binary),
        "changed_lines": {},
        "files": {},
        "languages": {},
    }
    for f in files:
        ranges = merge_ranges([n for n, _ in f_added_lines(f)])
        if ranges:
            facts["changed_lines"][f.path] = ranges
        info = {
            "status": f.status, "language": f.language, "test": f.test,
            "added": f.added, "deleted": f.deleted, "excluded": f.excluded,
        }
        if f.status == "renamed":
            info["old_path"] = f.old_path
        facts["files"][f.path] = info
        if not f.excluded and not f.binary:
            name = f.language or "other"
            facts["languages"][name] = facts["languages"].get(name, 0) + 1
    facts["tests_touched"] = any(
        not excluded_path(f.path) and (f.test or any(True for _ in f.removed_defs) or any(True for _ in f.added_defs))
        for f in files
    )
    return facts


def lizard_functions(path, code):
    try:
        import lizard
        return lizard.analyze_file.analyze_source_code(path, code).function_list
    except Exception:
        return None


def body_has_assertion(lines):
    return any(ASSERT_RE.search(l) and not TRIVIAL_RE.search(l) for l in lines)


def head_body(f, name_no, start_no, texts, group):
    """Lines of the test whose definition starts at START_NO (1-based) in TEXTS."""
    funcs = lizard_functions(f.path, "\n".join(texts))
    best = None
    for fn in funcs or []:
        if fn.start_line <= name_no <= fn.end_line:
            if best is None or fn.end_line - fn.start_line < best.end_line - best.start_line:
                best = fn
    if best is not None:
        return texts[start_no - 1:best.end_line]
    later = [s + 1 for s, _, _ in find_defs(texts, group) if s + 1 > start_no]
    return texts[start_no - 1:(later[0] - 1) if later else len(texts)]


def literal_quotes(path):
    ext = ext_of(path)
    if ext == "rs":
        return '"'
    if ext in ("js", "jsx", "mjs", "cjs", "ts", "tsx", "mts", "cts", "vue", "svelte", "go", "kt", "kts"):
        return "\"'`"
    return "\"'"


def inside_literal(text, pos, quotes):
    """True when POS sits inside a quoted string on this line (quote parity, escapes honored)."""
    state = None
    i = 0
    while i < pos:
        c = text[i]
        if state and c == "\\":
            i += 2
            continue
        if c in quotes:
            state = c if state is None else (None if state == c else state)
        i += 1
    return state is not None


def code_match(regex, text, quotes):
    return next((m for m in regex.finditer(text) if not inside_literal(text, m.start(), quotes)), None)


def code_find(needle, text, quotes):
    pos = text.find(needle)
    while pos >= 0:
        if not inside_literal(text, pos, quotes):
            return pos
        pos = text.find(needle, pos + 1)
    return -1


def has_test_markers(f, contents):
    if not f.group:
        return False
    head = contents.head(f.path) if contents else None
    if head is not None and find_defs(head.split("\n"), f.group):
        return True
    return any(find_defs([l[1] for l in h.lines], f.group) for h in f.hunks)


def tripwires(files, contents):
    groups = {}

    def add(kind, f, line, base_line, detail, text):
        g = groups.setdefault((f.path, kind), {
            "kind": kind, "severity": SEVERITY[kind], "file": f.path, "items": [],
        })
        g["items"].append({"line": line, "base_line": base_line, "detail": detail, "text": text.strip()})

    for f in files:
        if f.binary or excluded_path(f.path):
            continue
        removed_names = set(d[0] for d in f.removed_defs)
        added_names = set(d[0] for d in f.added_defs)
        deleted_file = f.status == "deleted"
        gone = [d for d in f.removed_defs if d[0] not in added_names]
        if deleted_file and (f.test or f.removed_defs):
            add("test-deleted", f, 1, 1, "test file deleted", f.path)
        else:
            for name, h, old_no, text, _ in gone:
                add("test-deleted", f, max(h.new_start, 1), old_no, name, text)
        group_ok = f.language in SKIP_LANGS
        if group_ok:
            quotes = literal_quotes(f.path)
            for no, text in f_added_lines(f):
                if any(code_match(r, text, quotes) for r in SKIP_RES) or (
                        f.language == "ruby" and RUBY_SKIP_RE.search(text)):
                    add("test-skipped", f, no, None, "skip marker", text)
        if f.test or has_test_markers(f, contents):
            rem = [(o, t, h) for o, t, h in f_removed_lines(f) if ASSERT_RE.search(t)]
            adds = [(n, t) for n, t in f_added_lines(f) if ASSERT_RE.search(t)]
            if len(rem) > len(adds):
                o, t, h = rem[0]
                line, base = (1, 1) if deleted_file else (max(h.new_start, 1), o)
                add("assertion-lost", f, line, base, "-%d net assertions" % (len(rem) - len(adds)), t)
        if f.group and not deleted_file:
            head = contents.head(f.path) if contents else None
            for name, h, start_no, text, name_no in f.added_defs:
                if name in removed_names:
                    continue
                if head is not None:
                    body = head_body(f, name_no, start_no, head.split("\n"), f.group)
                else:
                    seq = [l for l in h.lines if l[0] in " +"]
                    texts = [l[1] for l in seq]
                    idx = [l[3] for l in seq].index(start_no)
                    later = [s for s, _, _ in find_defs(texts, f.group) if s > idx]
                    body = texts[idx:later[0] if later else len(texts)]
                if not body_has_assertion(body):
                    add("test-no-assertion", f, start_no, None,
                        "no assertion in the body; helper calls may assert", text)
        ext = ext_of(f.path)
        for exts, pats in SUPPRESS:
            if ext in exts:
                quotes = literal_quotes(f.path)
                for no, text in f_added_lines(f):
                    hit = next((p for p in pats if code_find(p, text, quotes) >= 0), None)
                    if hit:
                        add("suppression", f, no, None, hit, text)
        gate_tripwires(f, add)
    out = []
    for key in sorted(groups):
        g = groups[key]
        g["items"].sort(key=lambda i: (i["line"], i["base_line"] or 0, i["detail"]))
        out.append(g)
    return out


def matches_any(path, patterns):
    base = os.path.basename(path)
    return any(
        fnmatch.fnmatchcase(base, p) or fnmatch.fnmatchcase(path, p) or fnmatch.fnmatchcase(path, "*/" + p)
        for p in patterns
    )


def gate_tripwires(f, add):
    if not matches_any(f.path, GATE_PATTERNS):
        return
    base = os.path.basename(f.path)
    eslint = base.startswith(".eslintrc") or base.startswith("eslint.config.")
    added = f_added_lines(f)
    removed = f_removed_lines(f)
    for no, text in added:
        m = next((m for m in (r.search(text) for r in GATE_ADD_RES) if m), None)
        hit = m.group(0) if m else None
        if hit is None and eslint and ESLINT_OFF_RE.search(text):
            hit = "rule off"
        if hit:
            add("gate-loosened", f, no, None, "added " + hit, text)
    old_vals = {}
    for o, text, h in removed:
        m = KEY_NUM_RE.match(text)
        if m:
            old_vals.setdefault(m.group(1), (float(m.group(2)), o, h))
    for no, text in added:
        m = KEY_NUM_RE.match(text)
        if not m or m.group(1) not in old_vals:
            continue
        key, new = m.group(1), float(m.group(2))
        old, o, _ = old_vals[key]
        if (LOWER_KEY_RE.search(key) and new < old) or (UPPER_KEY_RE.match(key) and new > old):
            add("gate-loosened", f, no, o, "%s %g -> %g" % (key, old, new), text)
    if matches_any(f.path, CI_PATTERNS):
        added_text = set(t.strip() for _, t in added)
        for o, text, h in removed:
            if CI_RUN_RE.search(text) and text.strip() not in added_text:
                add("gate-loosened", f, max(h.new_start, 1), o, "removed CI step", text)


def comment_pointers(files):
    out = []
    for f in files:
        markers = COMMENT_MARKERS.get(f.language)
        if f.excluded or f.binary or not markers:
            continue
        for no, text in f_added_lines(f):
            s = text.strip()
            marker = next((m for m in sorted(markers, key=len, reverse=True) if s.startswith(m)), None)
            if marker is None or s.startswith("#!") or re.match(r"#\s*(?:-\*-|coding[:=]|vim:)", s):
                continue
            inner = s[len(marker):].strip()
            if DIRECTIVE_RE.search(s):
                kind = "directive"
            elif marker in LINE_MARKERS and (CODE_COMMENT_RE.match(inner) or inner.endswith((";", "{", "}", ")"))):
                kind = "code"
            else:
                kind = "comment"
            out.append({"file": f.path, "line": no, "kind": kind, "text": s})
    out.sort(key=lambda p: (p["file"], p["line"]))
    return out


def dep_name(line):
    return NAME_SPLIT_RE.split(line.strip(), 1)[0].lower()


def toml_deps(text, kind):
    try:
        import tomllib
    except ImportError:
        return None
    try:
        d = tomllib.loads(text)
    except Exception:
        return None
    out = {}

    def table(t):
        for k, v in (t or {}).items():
            if k != "python":
                out[k] = v if isinstance(v, str) else json.dumps(v, sort_keys=True)

    def reqs(lst):
        for r in lst or []:
            if isinstance(r, str):
                out[dep_name(r)] = r

    if kind == "cargo":
        for k in ("dependencies", "dev-dependencies", "build-dependencies"):
            table(d.get(k))
        table(d.get("workspace", {}).get("dependencies"))
        for t in d.get("target", {}).values():
            for k in ("dependencies", "dev-dependencies", "build-dependencies"):
                table(t.get(k))
    else:
        reqs(d.get("project", {}).get("dependencies"))
        for v in d.get("project", {}).get("optional-dependencies", {}).values():
            reqs(v)
        table(d.get("tool", {}).get("poetry", {}).get("dependencies"))
        for v in d.get("dependency-groups", {}).values():
            reqs(v)
    return out


def dependency_pointers(files, contents):
    out, unmeasured = [], {}

    def need_contents(f, why):
        unmeasured[f.path] = why

    for f in files:
        if f.excluded or f.binary or f.status == "deleted":
            continue
        base = os.path.basename(f.path)
        added = f_added_lines(f)
        removed = [t for _, t, _ in f_removed_lines(f)]
        line_of = lambda needle: next((n for n, t in added if needle in t), 1)
        if base == "package.json":
            if not (contents and contents.can_head()):
                need_contents(f, "head contents not in the local clone")
                continue
            if f.status != "added" and not contents.can_base():
                need_contents(f, "base not in the local clone")
                continue
            try:
                head = json.loads(contents.head(f.path) or "{}")
                old = json.loads(contents.base(f.old_path or f.path) or "{}") if f.status != "added" else {}
            except ValueError:
                need_contents(f, "package.json is not valid JSON")
                continue
            keys = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
            before = set(n for k in keys for n in (old.get(k) or {}))
            for k in keys:
                for n, spec in sorted((head.get(k) or {}).items()):
                    if n not in before:
                        out.append({"file": f.path, "line": line_of('"%s"' % n), "name": n, "spec": str(spec)})
                        before.add(n)
        elif re.match(r"(requirements|constraints)[\w.\-]*\.txt$", base):
            gone = set(dep_name(t) for t in removed)
            for no, t in added:
                s = t.strip()
                if s and not s.startswith(("#", "-")) and dep_name(s) not in gone:
                    out.append({"file": f.path, "line": no, "name": dep_name(s), "spec": s})
        elif base == "go.mod":
            rx = re.compile(r"^\s*(?:require\s+)?([\w.\-/]+)\s+(v\S+)")
            gone = set(m.group(1) for m in (rx.match(t) for t in removed) if m)
            for no, t in added:
                m = rx.match(t)
                if m and m.group(1) not in gone:
                    out.append({"file": f.path, "line": no, "name": m.group(1), "spec": m.group(2)})
        elif base in ("Cargo.toml", "pyproject.toml"):
            kind = "cargo" if base == "Cargo.toml" else "py"
            if not (contents and contents.can_head()) or (f.status != "added" and not contents.can_base()):
                need_contents(f, "base not in the local clone")
                continue
            head = toml_deps(contents.head(f.path) or "", kind)
            old = toml_deps(contents.base(f.old_path or f.path) or "", kind) if f.status != "added" else {}
            if head is None or old is None:
                need_contents(f, "tomllib needs Python 3.11 or the manifest does not parse")
                continue
            for n in sorted(set(head) - set(old)):
                out.append({"file": f.path, "line": line_of(n), "name": n, "spec": head[n]})
        elif base == "Gemfile":
            rx = re.compile(r"gem\s+['\"]([^'\"]+)['\"]")
            gone = set(m.group(1) for m in (rx.search(t) for t in removed) if m)
            for no, t in added:
                m = rx.search(t)
                if m and m.group(1) not in gone:
                    out.append({"file": f.path, "line": no, "name": m.group(1), "spec": t.strip()})
    out.sort(key=lambda p: (p["file"], p["line"], p["name"]))
    return out, unmeasured


def repo_relative(path, repo):
    """PATH relative to REPO, resolving symlinked prefixes; PATH unchanged when it lies elsewhere."""
    if not (repo and os.path.isabs(path)):
        return path
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(repo))
    return path if rel.startswith("..") else rel


def parse_coverage(path, repo):
    """-> {file: {line: count}} or None when the file is not understood."""
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    lines = [l.rstrip("\r") for l in text.split("\n") if l.strip()]
    if not lines:
        return None
    cov = {}

    def norm(p, mod=None):
        p = repo_relative(p.strip(), repo)
        if mod and p.startswith(mod + "/"):
            p = p[len(mod) + 1:]
        return p[2:] if p.startswith("./") else p

    if lines[0].startswith("mode:"):
        mod = None
        gomod = os.path.join(repo or "", "go.mod")
        if repo and os.path.isfile(gomod):
            with open(gomod, encoding="utf-8", errors="replace") as fh:
                m = re.search(r"^module\s+(\S+)", fh.read(), re.M)
                mod = m.group(1) if m else None
        rx = re.compile(r"^(.+):(\d+)\.\d+,(\d+)\.\d+ \d+ (\d+)$")
        for l in lines[1:]:
            m = rx.match(l)
            if not m:
                return None
            d = cov.setdefault(norm(m.group(1), mod), {})
            for n in range(int(m.group(2)), int(m.group(3)) + 1):
                d[n] = max(d.get(n, 0), int(m.group(4)))
        return cov
    if any(l.startswith("SF:") for l in lines):
        cur = None
        for l in lines:
            if l.startswith("SF:"):
                cur = cov.setdefault(norm(l[3:]), {})
            elif l.startswith("DA:") and cur is not None:
                m = re.match(r"DA:(\d+),(-?\d+)", l)
                if not m:
                    return None
                cur[int(m.group(1))] = max(cur.get(int(m.group(1)), 0), int(m.group(2)))
        return cov or None
    for l in lines:
        m = re.match(r"^(.+):(\d+)$", l.strip())
        if not m:
            return None
        cov.setdefault(norm(m.group(1)), {})[int(m.group(2))] = 0
    return cov


def coverage_language_names(value):
    """Parse --coverage-langs; a name `facts.languages` never uses is a usage error, never a silent skip."""
    if not value:
        return None
    known = set(EXT_LANG.values()) | set(NAME_LANG.values())
    names = set(x for x in value.split(",") if x)
    bad = sorted(names - known)
    if bad:
        die("unknown language in --coverage-langs: %s (accepted: %s)" % (", ".join(bad), ", ".join(sorted(known))))
    return names


def coverage_scope(files, changed_lines, cov, tool_langs=None):
    """-> (applicable, reason, languages): whether COV can vouch for the changed code, per language.

    TOOL_LANGS, when given, names the languages the repo's coverage tool covers; a language outside it is
    reported as such and never blocks."""
    reported = set(ext_of(p) for p in cov)
    code = [f for f in files if not (f.excluded or f.binary or f.test or f.status == "deleted")
            and f.language and f.language not in DOC_LANGS and f.path in changed_lines]
    langs = {}
    for f in code:
        coverable = f.language not in NO_COVERAGE_LANGS or ext_of(f.path) in reported
        if tool_langs is not None and f.language not in tool_langs and ext_of(f.path) not in reported:
            langs.setdefault(f.language, "outside tool scope")
        elif not coverable:
            langs.setdefault(f.language, "not coverable")
        elif ext_of(f.path) in reported:
            langs[f.language] = "measured"
        elif langs.get(f.language) != "measured":
            langs[f.language] = "no evidence"
    coverable = [l for l, st in langs.items() if st not in ("not coverable", "outside tool scope")]
    if not coverable:
        exts = sorted(set("." + ext_of(f.path) for f in code))
        return False, "no changed language has coverage (%s)" % " ".join(exts), langs
    if not any(cov.values()):
        return True, "coverage report holds no line data", langs
    missing = sorted(l for l in coverable if langs[l] == "no evidence")
    if missing:
        return True, "coverage report has no evidence for: %s" % ", ".join(missing), langs
    return True, None, langs


def uncovered_pointers(files, changed_lines, cov):
    out = []
    reported_exts = set(ext_of(p) for p in cov)
    for f in files:
        if f.excluded or f.binary or f.status == "deleted" or f.test:
            continue
        if f.path in cov and not cov[f.path] and f.path in changed_lines:
            out.append({"file": f.path, "lines": "all", "reason": "no line data for the file in the coverage report"})
        elif f.path in cov:
            nums = [n for r in changed_lines.get(f.path, []) for n in range(r[0], r[1] + 1)]
            bad = [n for n in nums if cov[f.path].get(n) == 0]
            if bad:
                out.append({"file": f.path, "lines": bad})
        elif ext_of(f.path) in reported_exts and f.path in changed_lines:
            out.append({"file": f.path, "lines": "all", "reason": "absent from coverage report"})
    out.sort(key=lambda p: p["file"])
    return out


def trivial_line(s):
    return (
        len(s.replace(" ", "")) < 10 or not re.search(r"\w", s) or TRIVIAL_IMPORT_RE.match(s) is not None
    )


def comment_only(s, lang):
    return any(s.startswith(m) for m in COMMENT_MARKERS.get(lang, ()))


def norm_lines(items, lang):
    """items: [(no, text)] -> [(no, normalized)] without trivial lines."""
    out = []
    for no, t in items:
        s = t.strip()
        if not trivial_line(s) and not comment_only(s, lang):
            out.append((no, s))
    return out


def windows(seq, size=4):
    return [(i, tuple(s for _, s in seq[i:i + size])) for i in range(len(seq) - size + 1)]


def added_runs(f):
    runs, cur = [], []
    for no, t in f_added_lines(f):
        if cur and no != cur[-1][0] + 1:
            runs.append(cur)
            cur = []
        cur.append((no, t))
    if cur:
        runs.append(cur)
    return runs


def lizard_duplicates(files, contents, changed_lines):
    try:
        import lizard_languages
        import lizard  # noqa: F401
    except ImportError:
        return []
    cand = [f for f in files if not f.excluded and not f.test and not f.binary and f.status != "deleted"
            and lizard_languages.get_reader_for(f.path) is not None]
    if len(cand) == 0:
        return []
    tmp = tempfile.mkdtemp(prefix="dm-dup-")
    try:
        names = []
        for f in cand:
            text = contents.head(f.path) if contents else None
            if text is None:
                continue
            if unsafe_path(f.path):
                continue
            dest = os.path.join(tmp, f.path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(text)
            names.append(f.path)
        if not names:
            return []
        p = subprocess.run(
            [sys.executable, "-I", "-m", "lizard", "-Eduplicate"] + sorted(names), cwd=tmp,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True,
        )
        blocks, copies, state = [], [], 0
        for l in p.stdout.split("\n"):
            if l.startswith("Duplicate block:"):
                copies, state = [], 1
            elif state == 1 and l.startswith("^^^^"):
                blocks.append(copies)
                state = 0
            elif state == 1:
                m = re.match(r"^(.+):(\d+) ~ (\d+)$", l.strip())
                if m:
                    copies.append((m.group(1), int(m.group(2)), int(m.group(3))))
        out = []
        for copies in blocks:
            for k, (path, s, e) in enumerate(copies):
                rngs = changed_lines.get(path, [])
                if not any(r[0] <= e and s <= r[1] for r in rngs):
                    continue
                other = copies[1 - k] if len(copies) == 2 else next(c for j, c in enumerate(copies) if j != k)
                out.append({
                    "file": path, "line": s, "lines": e - s + 1,
                    "match": {"file": other[0], "line": other[1], "where": "diff"}, "source": "lizard",
                })
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def duplicate_pointers(files, contents, repo, base, changed_lines):
    live = [f for f in files if not f.excluded and not f.test and not f.binary and f.status != "deleted"]
    wins = []
    deleted_old = {}
    removed_keys = set()
    for f in files:
        removed = [(o, t) for o, t, _ in f_removed_lines(f)]
        if removed:
            deleted_old[f.old_path or f.path] = set(o for o, _ in removed)
            rr, cur = [], []
            for o, t in removed:
                if cur and o != cur[-1][0] + 1:
                    rr.append(cur)
                    cur = []
                cur.append((o, t))
            rr.append(cur)
            for run in rr:
                for _, key in windows(norm_lines(run, f.language)):
                    removed_keys.add(key)
    for f in live:
        for rid, run in enumerate(added_runs(f)):
            seq = norm_lines(run, f.language)
            for i, key in windows(seq):
                wins.append({"file": f.path, "run": (f.path, rid), "idx": i, "no": seq[i][0], "key": key,
                             "end": seq[i + 3][0], "n": len(seq)})
    found = []
    by_key = {}
    for w in wins:
        by_key.setdefault(w["key"], []).append(w)
    for key, ws in by_key.items():
        if key in removed_keys:
            continue
        ws.sort(key=lambda w: (w["file"], w["no"]))
        first = ws[0]
        for w in ws[1:]:
            if w["file"] == first["file"] and abs(w["no"] - first["no"]) < 4:
                continue
            found.append((w, {"file": first["file"], "line": first["no"], "where": "diff"}))
    status = {"status": "measured"}
    if repo and base:
        firsts = {}
        for w in wins:
            firsts.setdefault(w["key"][0], 0)
        pats = sorted(firsts, key=lambda s: (-len(s), s))[:500]
        if pats:
            fd, pf = tempfile.mkstemp(prefix="dm-pat-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(pats) + "\n")
                p = git(repo, "grep", "-F", "-l", "-z", "-f", pf, base, "--")
            finally:
                os.unlink(pf)
            hits = sorted(h.decode("utf-8", "replace") for h in p.stdout.split(b"\0") if h)
            hits = [h.split(":", 1)[1] if ":" in h[:60] and h.startswith(base) else h for h in hits]
            hits = [h for h in hits if not excluded_path(h) and not is_test_path(h)]
            blobs = read_blobs(repo, ["%s:%s" % (base, h) for h in hits])
            keyset = set(w["key"] for w in wins)
            for h in hits:
                text = as_text(blobs.get("%s:%s" % (base, h)))
                if text is None:
                    continue
                items = [(n + 1, t) for n, t in enumerate(text.split("\n"))]
                seq = norm_lines(items, lang_of(h))
                dele = deleted_old.get(h, set())
                for i, key in windows(seq):
                    if key not in keyset:
                        continue
                    if all(seq[j][0] in dele for j in range(i, i + 4)):
                        continue
                    for w in by_key[key]:
                        found.append((w, {"file": h, "line": seq[i][0], "where": "base"}))
    else:
        status = {"status": "partial", "reason": "no base in the local clone: diff-internal only"}
    found.sort(key=lambda fm: (fm[0]["file"], fm[0]["no"], fm[1]["where"] != "base", fm[1]["file"], fm[1]["line"]))
    blocks = []
    seen = set()
    for w, m in found:
        k = (w["file"], w["no"])
        if k in seen:
            continue
        seen.add(k)
        last = blocks[-1] if blocks else None
        if (last and last["file"] == w["file"] and last["_run"] == w["run"] and last["match"]["file"] == m["file"]
                and last["match"]["where"] == m["where"] and w["no"] <= last["_end"]):
            last["_end"] = max(last["_end"], w["end"])
            last["lines"] = last["_n"] = last["_n"] + (1 if w["end"] > last["_prev_end"] else 0)
            last["_prev_end"] = w["end"]
            continue
        blocks.append({"file": w["file"], "line": w["no"], "lines": 4, "match": m, "source": "window",
                       "_run": w["run"], "_end": w["end"], "_n": 4, "_prev_end": w["end"]})
    out = []
    for b in blocks:
        out.append({k: v for k, v in b.items() if not k.startswith("_")})
    liz = lizard_duplicates(files, contents, changed_lines) if contents else []
    merged = []
    for z in liz:
        z_end = z["line"] + z["lines"] - 1
        keep = []
        for b in out:
            b_end = b["line"] + b["lines"] - 1
            if b["file"] == z["file"] and b["line"] <= z_end and z["line"] <= b_end:
                continue
            keep.append(b)
        out = keep
        merged.append(z)
    out += merged
    out.sort(key=lambda b: (-b["lines"], b["file"], b["line"]))
    return out, status


def lizard_reader(path):
    try:
        import lizard_languages
    except ImportError:
        return "missing"
    return lizard_languages.get_reader_for(path) is not None


def complexity_pointers(files, contents, changed_lines):
    try:
        import lizard  # noqa: F401
    except ImportError:
        return [], {"status": "unmeasured", "reason": "lizard not installed"}
    if not (contents and contents.can_head() and contents.can_base()):
        return [], {"status": "unmeasured", "reason": "base not in the local clone"}
    out, unmeasured, measured = [], {}, 0
    for f in files:
        if f.excluded or f.binary or f.status == "deleted" or f.language in DOC_LANGS or ext_of(f.path) in PLAIN_EXTS or (
                f.language is None and not ext_of(f.path)):
            continue
        if not lizard_reader(f.path):
            unmeasured[ext_of(f.path) and "." + ext_of(f.path) or os.path.basename(f.path)] = (
                "lizard has no reader for %s" % (ext_of(f.path) and "." + ext_of(f.path) or os.path.basename(f.path)))
            continue
        head = contents.head(f.path)
        if head is None:
            continue
        base_text = "" if f.status == "added" else contents.base(f.old_path or f.path) or ""
        hf = lizard_functions(f.path, head)
        bf = lizard_functions(f.old_path or f.path, base_text) if base_text else []
        if hf is None or bf is None:
            unmeasured[f.path] = "lizard failed on %s" % f.path
            continue
        measured += 1
        by_long = {}
        by_name = {}
        for fn in bf:
            by_long.setdefault(fn.long_name, fn)
            by_name.setdefault(fn.name, fn)
        rngs = changed_lines.get(f.path, [])
        for fn in hf:
            if not any(r[0] <= fn.end_line and fn.start_line <= r[1] for r in rngs):
                continue
            old = by_long.get(fn.long_name) or by_name.get(fn.name)
            if old is None:
                out.append({"file": f.path, "function": fn.name, "line": fn.start_line, "before": 0,
                            "after": fn.cyclomatic_complexity, "status": "new"})
            elif fn.cyclomatic_complexity > old.cyclomatic_complexity:
                out.append({"file": f.path, "function": fn.name, "line": fn.start_line,
                            "before": old.cyclomatic_complexity, "after": fn.cyclomatic_complexity,
                            "status": "changed"})
    out.sort(key=lambda p: (-(p["after"] - p["before"]), p["file"], p["line"]))
    if measured == 0:
        if unmeasured:
            return out, {"status": "unmeasured", "unmeasured": dict(sorted(unmeasured.items())),
                         "reason": "no changed file lizard reads"}
        return out, {"status": "unmeasured", "reason": "no changed file lizard reads"}
    if unmeasured:
        return out, {"status": "partial", "unmeasured": dict(sorted(unmeasured.items()))}
    return out, {"status": "measured"}


def scc_version():
    try:
        p = subprocess.run(["scc", "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
    except OSError:
        return None
    m = re.search(r"(\d+\.\d+\.\d+)", p.stdout)
    return m.group(1) if m else None


def scc_files(root):
    """-> {relative path: (code, comment, complexity)} for every file scc recognizes under ROOT; None when scc fails."""
    try:
        p = subprocess.run(
            ["scc", "--format", "json", "--by-file", "--no-cocomo", "--no-gitignore", "--no-ignore", "."],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        data = json.loads(p.stdout.decode("utf-8", "replace") or "[]")
        if p.returncode != 0 or not isinstance(data, list):
            return None
        out = {}
        for lang in data:
            for fi in lang.get("Files", []):
                loc = fi["Location"]
                loc = loc[2:] if loc.startswith("./") else loc
                out[loc] = (fi.get("Code", 0), fi.get("Comment", 0), fi.get("Complexity", 0))
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return None
    return out


def materialize(root, items):
    for path, text in items.items():
        if text is None:
            continue
        if unsafe_path(path):
            die("refusing to write outside %s: %s" % (root, path))
        dest = os.path.join(root, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(text)


def hotspot_pointers(files, repo, base, base_is_commit, changed_paths):
    if not shutil.which("scc"):
        return [], {"status": "unmeasured", "reason": "scc not installed"}
    if not (repo and base):
        return [], {"status": "unmeasured", "reason": "base not in the local clone"}
    if not base_is_commit:
        return [], {"status": "unmeasured", "reason": "history needs a commit base"}
    if git_out(repo, "rev-parse", "--is-shallow-repository") == "true":
        return [], {"status": "unmeasured", "reason": "shallow clone"}
    p = git(repo, "log", "-n", "1000", "--no-merges", "--no-renames", "--format=", "--numstat", "-z", base, "--")
    ls = git(repo, "ls-tree", "-r", "--name-only", "-z", base)
    if p.returncode != 0 or ls.returncode != 0:
        return [], {"status": "unmeasured", "reason": "git history could not be read"}
    churn = {}
    for rec in p.stdout.split(b"\0"):
        rec = rec.lstrip(b"\n")
        parts = rec.decode("utf-8", "replace").split("\t", 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        churn[parts[2]] = churn.get(parts[2], 0) + int(parts[0]) + int(parts[1])
    tree = set(x.decode("utf-8", "replace") for x in ls.stdout.split(b"\0") if x)
    paths = sorted((c, p_) for p_, c in churn.items() if p_ in tree and not excluded_path(p_))
    paths = [p_ for c, p_ in sorted(paths, key=lambda x: (-x[0], x[1]))][:2000]
    tmp = tempfile.mkdtemp(prefix="dm-hot-")
    try:
        blobs = read_blobs(repo, ["%s:%s" % (base, x) for x in paths])
        materialize(tmp, dict((x, as_text(blobs.get("%s:%s" % (base, x)))) for x in paths))
        stats = scc_files(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if stats is None:
        return [], {"status": "unmeasured", "reason": "scc output not understood"}
    scored = [(churn[x] * stats[x][2], x) for x in paths if x in stats and churn[x] * stats[x][2] > 0]
    scored.sort(key=lambda s: (-s[0], s[1]))
    n = len(scored)
    top = scored[:int(math.ceil(n / 10.0))] if n else []
    out = []
    for rank, (score, x) in enumerate(top, 1):
        if x in changed_paths:
            out.append({"file": x, "rank": rank, "of": n, "churn": churn[x], "complexity": stats[x][2]})
    out.sort(key=lambda h: (h["rank"], h["file"]))
    return out, {"status": "measured"}


def comment_deltas(files, contents):
    if not shutil.which("scc"):
        return [], "scc not installed"
    if not (contents and contents.can_head() and contents.can_base()):
        return [], "base not in the local clone"
    live = [f for f in files if not f.excluded and not f.binary]
    tb, th = tempfile.mkdtemp(prefix="dm-cb-"), tempfile.mkdtemp(prefix="dm-ch-")
    try:
        materialize(tb, dict((f.old_path or f.path, contents.base(f.old_path or f.path))
                             for f in live if f.status != "added"))
        materialize(th, dict((f.path, contents.head(f.path)) for f in live if f.status != "deleted"))
        sb, sh = scc_files(tb), scc_files(th)
    finally:
        shutil.rmtree(tb, ignore_errors=True)
        shutil.rmtree(th, ignore_errors=True)
    if sb is None or sh is None:
        return [], "scc output not understood"
    out = []
    for f in live:
        h = sh.get(f.path)
        b = sb.get(f.old_path or f.path)
        if h is None and b is None:
            continue
        d = (h[1] if h else 0) - (b[1] if b else 0)
        if d:
            out.append({"file": f.path, "delta": d})
    out.sort(key=lambda x: x["file"])
    return out, None


def tool_versions():
    v = git_out(os.getcwd(), "--version") or ""
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", v)
    liz = None
    try:
        import lizard
        liz = getattr(lizard, "version", None)
    except ImportError:
        pass
    return {"diff_metrics": SCHEMA, "git": m.group(1) if m else None, "lizard": liz, "scc": scc_version()}


def cmd_measure(args):
    tool_langs = coverage_language_names(args.coverage_langs)
    with open(args.diff, "rb") as fh:
        data = fh.read()
    repo = resolve_repo(args.repo) if args.repo else toplevel(os.getcwd())
    head = None
    if args.head:
        head = args.head
    elif args.index:
        head = "index"
    elif args.worktree:
        head = "worktree"
    if head and not repo:
        die("--worktree, --index and --head need a repository")
    base = None
    base_is_commit = False
    if args.base and repo:
        base = resolve_rev(repo, args.base)
        if base is None:
            die("base does not resolve: %s" % args.base)
        base_is_commit = git(repo, "cat-file", "-t", base).stdout.strip() == b"commit"
    head_id = head
    if head and head not in ("worktree", "index"):
        head_id = resolve_rev(repo, head)
        if head_id is None:
            die("head does not resolve: %s" % head)
    contents = Contents(repo, base, head_id) if repo else None
    files = analyze_files(parse_diff(data), contents)
    facts = build_facts(files)
    cl = facts["changed_lines"]
    checks = {"tripwires": {"status": "measured"}}
    trips = tripwires(files, contents)
    pointers = {}
    pointers["complexity"], checks["complexity"] = complexity_pointers(files, contents, cl)
    changed_paths = set(f.path for f in files if not f.excluded and not f.binary and f.status != "deleted")
    pointers["hotspots"], checks["hotspots"] = hotspot_pointers(files, repo, base, base_is_commit, changed_paths)
    pointers["duplicates"], checks["duplicates"] = duplicate_pointers(
        files, contents if contents and contents.can_head() else None, repo, base, cl)
    pointers["comments"] = comment_pointers(files)
    checks["comments"] = {"status": "measured"}
    pointers["comment_deltas"], why = comment_deltas(files, contents)
    if why:
        checks["comments"] = {"status": "partial", "unmeasured": {"comment_deltas": why}}
    pointers["dependencies"], dep_un = dependency_pointers(files, contents)
    checks["dependencies"] = {"status": "partial", "unmeasured": dict(sorted(dep_un.items()))} if dep_un else {"status": "measured"}
    cov_sha = None
    pointers["uncovered"] = []
    if args.coverage:
        try:
            with open(args.coverage, "rb") as fh:
                cov_sha = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            cov_sha = None
        cov = parse_coverage(args.coverage, repo) if cov_sha else None
        if cov is None:
            checks["uncovered"] = {"status": "unmeasured", "reason": "coverage file not understood"}
        else:
            applicable, gap, langs = coverage_scope(files, cl, cov, tool_langs)
            pointers["uncovered"] = uncovered_pointers(files, cl, cov)
            if gap:
                checks["uncovered"] = {"status": "unmeasured", "reason": gap, "applicable": applicable, "languages": langs}
            else:
                checks["uncovered"] = {"status": "measured", "languages": langs}
    else:
        checks["uncovered"] = {"status": "unmeasured", "reason": "no coverage handed in"}
    result = {
        "schema": SCHEMA,
        "tools": tool_versions(),
        "target": {
            "diff_sha256": hashlib.sha256(data).hexdigest(), "repo": repo if (repo and (base or head)) else None,
            "base": base, "head": head_id, "coverage_sha256": cov_sha,
        },
        "facts": facts,
        "checks": checks,
        "tripwires": trips,
        "pointers": pointers,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, sort_keys=True, indent=2)
        fh.write("\n")
    counts = " ".join("%s=%d" % (k, len(pointers[k])) for k in
                      ("complexity", "hotspots", "duplicates", "comments", "dependencies", "uncovered"))
    un = []
    for name in sorted(checks):
        c = checks[name]
        if c["status"] != "measured":
            why = c.get("reason") or "; ".join("%s: %s" % kv for kv in sorted(c.get("unmeasured", {}).items()))
            un.append("%s (%s%s)" % (name, c["status"], ": " + why if why else ""))
    print("diff-metrics: S=%d F=%d tripwires=%d (groups %d) pointers: %s" % (
        facts["S"], facts["F"], sum(len(g["items"]) for g in trips), len(trips), counts))
    print("unmeasured: %s" % ("; ".join(un) if un else "none"))
    print("wrote %s" % args.out)
    return 0


POINTER_HEADER = "Pointers, ranked: where to look first, never a finding on their own."
KIND_TEXT = {
    "test-deleted": "%d test definition(s) removed with no replacement in this file",
    "test-skipped": "%d skip marker(s) added",
    "assertion-lost": "assertions removed without replacement (%s)",
    "test-no-assertion": "%d new test(s) with no assertion in the body (helper calls may assert, check before confirming)",
    "suppression": "%d lint or type suppression(s) added",
    "gate-loosened": "%d gate setting(s) loosened",
}
KIND_CONF = {"suppression": "medium", "test-no-assertion": "medium"}


def check_note(check, name, label=None):
    c = check or {}
    label = label or name
    if c.get("status") == "unmeasured":
        why = c.get("reason") or "; ".join(sorted(set(c.get("unmeasured", {}).values())))
        return "%s: unmeasured (%s)" % (label, why)
    if c.get("unmeasured"):
        exts = sorted(c["unmeasured"])
        return "%s: unmeasured for %s" % (label, " ".join(exts))
    return None


def write_lines(path, lines, notes):
    body = [POINTER_HEADER] + (lines or ["none"]) + [n for n in notes if n]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body) + "\n")


def tripwire_candidate(g):
    items = g["items"]
    first = items[0]
    if g["kind"] == "assertion-lost":
        summary = KIND_TEXT[g["kind"]] % first["detail"]
    else:
        summary = KIND_TEXT[g["kind"]] % len(items)
    ev = []
    for i in items:
        loc = ("base line %d" % i["base_line"]) if i["base_line"] and g["kind"] in ("test-deleted", "assertion-lost", "gate-loosened") else ("line %d" % i["line"])
        ev.append("`%s` (%s)" % (i["text"], loc))
    return "\n".join([
        "[%s] %s:%d — tripwire %s: %s" % (g["severity"].upper(), g["file"], first["line"], g["kind"], summary),
        "evidence: " + "; ".join(ev),
        "grounding: metric: %s %s:%d %d %s" % (g["kind"], g["file"], first["line"], len(items),
                                                "item" if len(items) == 1 else "items"),
        "confidence: " + KIND_CONF.get(g["kind"], "high"),
    ])


def cmd_bundle(args):
    with open(args.metrics, encoding="utf-8") as fh:
        m = json.load(fh)
    with open(args.diff, "rb") as fh:
        diff = fh.read().decode("utf-8", "replace")
    os.makedirs(args.dir, exist_ok=True)
    d = lambda name: os.path.join(args.dir, name)
    ptr, chk, facts = m["pointers"], m["checks"], m["facts"]
    stat = ["%d\t%d\t%s%s" % (i["added"], i["deleted"], p, " (excluded)" if i["excluded"] else "")
            for p, i in sorted(facts["files"].items())]
    with open(d("stat.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(stat or ["none"]) + "\n")
    cx = ["metric: complexity %s:%d %s %d -> %d (%s)" % (c["file"], c["line"], c["function"], c["before"], c["after"], c["status"])
          for c in ptr["complexity"] if c["status"] == "changed" or c["after"] >= 5]
    hot = ["metric: hotspot %s:1 rank %d of %d churn %d complexity %d" % (h["file"], h["rank"], h["of"], h["churn"], h["complexity"])
           for h in ptr["hotspots"]]
    unc = []
    for u in ptr["uncovered"]:
        if u["lines"] == "all":
            unc.append("metric: uncovered %s:1 all changed lines (%s)" % (u["file"], u["reason"]))
        else:
            for r in merge_ranges(u["lines"]):
                unc.append("metric: uncovered %s:%d %s" % (u["file"], r[0], "not covered" if r[0] == r[1] else "through line %d not covered" % r[1]))
    dup = ["metric: duplicate %s:%d %d lines also at %s:%d (%s, %s)" % (
        x["file"], x["line"], x["lines"], x["match"]["file"], x["match"]["line"], x["match"]["where"], x["source"])
        for x in ptr["duplicates"]]
    newfn = ["metric: new-function %s:%d %s" % (c["file"], c["line"], c["function"])
             for c in ptr["complexity"] if c["status"] == "new"]
    com = ["metric: %s %s:%d %s" % ("commented-out-code" if c["kind"] == "code" else "comment", c["file"], c["line"], c["text"])
           for c in ptr["comments"] if c["kind"] != "directive"]
    com += ["metric: comment-delta %s:1 %+d comment lines per scc" % (c["file"], c["delta"]) for c in ptr["comment_deltas"]]
    dep = ["metric: dependency %s:%d new %s %s" % (x["file"], x["line"], x["name"], x["spec"]) for x in ptr["dependencies"]]
    write_lines(d("pointers-correctness.txt"), cx + hot,
                [check_note(chk["complexity"], "complexity"), check_note(chk["hotspots"], "hotspots")])
    write_lines(d("pointers-tests.txt"), hot + unc,
                [check_note(chk["hotspots"], "hotspots"), check_note(chk["uncovered"], "uncovered")])
    write_lines(d("pointers-simplicity.txt"), dup + newfn + com,
                [check_note(chk["duplicates"], "duplicates"), check_note(chk["complexity"], "complexity"),
                 check_note(chk["comments"], "comments")])
    write_lines(d("pointers-architecture.txt"), dep, [check_note(chk["dependencies"], "dependencies")])
    keep = [l for l in diff.split("\n") if l.startswith(("diff --git", "+", "@@"))]
    with open(d("added.diff"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(keep) + ("\n" if keep else ""))
    cands = [tripwire_candidate(g) for g in m["tripwires"]]
    with open(d("tripwires.md"), "w", encoding="utf-8") as fh:
        fh.write(("\n\n".join(cands) if cands else "none") + "\n")
    return 0


def cmd_filter_lint(args):
    with open(args.metrics, encoding="utf-8") as fh:
        m = json.load(fh)
    cl = m["facts"]["changed_lines"]
    repo = (m["target"].get("repo") or "").rstrip("/")
    kept = located = unlocated = 0
    for raw in sys.stdin.read().split("\n"):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        mm = LINT_LOC_RE.match(line)
        if not mm:
            unlocated += 1
            continue
        located += 1
        path = repo_relative(mm.group(1), repo)
        while path.startswith("./"):
            path = path[2:]
        no = int(mm.group(2))
        if any(r[0] <= no <= r[1] for r in cl.get(path, [])):
            kept += 1
            sys.stdout.write(line + "\n")
    sys.stderr.write("filter-lint: kept=%d located=%d unlocated=%d\n" % (kept, located, unlocated))
    return 0


def cmd_snapshot(args):
    repo = resolve_repo(args.repo)
    if not repo:
        die("not a git repository")
    if git(repo, "rev-parse", "--verify", "--quiet", "HEAD^{commit}").returncode != 0:
        die("no commit yet: nothing to gate against")
    if git(repo, "ls-files", "-u").stdout.strip():
        die("the index holds unmerged entries: resolve them first")
    os.makedirs(args.index_dir, exist_ok=True)
    idx = os.path.join(os.path.abspath(args.index_dir), "index")
    real = git_out(repo, "rev-parse", "--path-format=absolute", "--git-path", "index")
    env = {"GIT_INDEX_FILE": idx}
    if real and os.path.exists(real):
        shutil.copyfile(real, idx)
    else:
        if git_out(repo, "config", "--bool", "core.sparseCheckout") == "true":
            die("sparse checkout without an index: cannot snapshot")
        if git(repo, "read-tree", "HEAD", env=env).returncode != 0:
            die("read-tree failed")
    plain = ["-c", "core.splitIndex=false", "-c", "core.untrackedCache=false"]
    if subprocess.run(["git"] + GIT_C + plain + ["add", "-A"], cwd=repo, env=git_env(env),
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
        die("git add -A failed")
    p = git(repo, "write-tree", env=env)
    if p.returncode != 0:
        die("write-tree failed")
    sys.stdout.write(p.stdout.decode().strip() + "\n")
    return 0


def repo_fingerprint(repo):
    h = hashlib.sha256()
    head = git_out(repo, "rev-parse", "--verify", "--quiet", "HEAD")
    h.update((head or "unborn").encode() + b"\0")
    h.update(git(repo, "ls-files", "--stage", "-z").stdout + b"\0")
    base = head or EMPTY_TREE
    h.update(build_diff(repo, base, "worktree", binary=True))
    return h.hexdigest()


def cmd_fingerprint(args):
    repo = resolve_repo(args.repo)
    if not repo:
        die("not a git repository")
    print(repo_fingerprint(repo))
    return 0


def token_pids(token):
    needle = ("TIMEBOX_TOKEN=%s" % token)
    pids = []
    if sys.platform == "darwin":
        ps = "/bin/ps" if os.path.exists("/bin/ps") else shutil.which("ps")
        if not ps:
            sys.stderr.write("diff-metrics: timebox cannot sweep escaped processes: no ps\n")
            return []
        try:
            p = subprocess.run([ps, "-Eww", "-o", "pid=,command=", "-U", str(os.getuid())],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True,
                               errors="replace")
        except OSError as e:
            sys.stderr.write("diff-metrics: timebox cannot sweep escaped processes: %s\n" % e)
            return []
        for l in p.stdout.split("\n"):
            if needle in l:
                pids.append(int(l.split(None, 1)[0]))
    else:
        for name in os.listdir("/proc"):
            if name.isdigit():
                try:
                    with open("/proc/%s/environ" % name, "rb") as fh:
                        if needle.encode() in fh.read():
                            pids.append(int(name))
                except OSError:
                    pass
    return [p for p in pids if p != os.getpid()]


def kill_all(pids, sig):
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except OSError:
        return False


def wait_gone(check, seconds):
    end = time.time() + seconds
    while time.time() < end and check():
        time.sleep(0.05)
    return not check()


def cmd_dirty(args):
    repo = resolve_repo(args.repo)
    if not repo:
        die("not a git repository")
    raw = git_ok(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames")
    paths = sorted(set(e[3:] for e in raw.decode("utf-8", "surrogateescape").split("\0") if len(e) > 3))
    write_nul_list(args.out, paths)
    print("paths=%d" % len(paths))
    return 0


def write_nul_list(path, paths):
    with open(path, "wb") as fh:
        for x in paths:
            fh.write(x.encode("utf-8", "surrogateescape") + b"\0")


def read_nul_list(path):
    with open(path, "rb") as fh:
        return [x.decode("utf-8", "surrogateescape") for x in fh.read().split(b"\0") if x]


def cmd_commit_set(args):
    repo = resolve_repo(args.repo)
    if not repo:
        die("not a git repository")
    changed = git_ok(repo, "diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", "--no-renames",
                     args.src, args.dst).decode("utf-8", "surrogateescape").split("\0")
    wanted = set(x for x in changed if x) | set(read_nul_list(args.dirty))
    indexed = set(x.decode("utf-8", "surrogateescape") for x in
                  git_ok(repo, "ls-files", "-z").split(b"\0") if x)
    keep = []
    for x in sorted(wanted):
        if unsafe_path(x):
            die("the commit set names a path outside the repository: %s" % x)
        if x in indexed or os.path.lexists(os.path.join(repo, x)):
            keep.append(x)
    write_nul_list(args.out, keep)
    print("paths=%d" % len(keep))
    return 0


class Interrupted(Exception):
    def __init__(self, sig):
        Exception.__init__(self, "interrupted by signal %d" % sig)
        self.sig = sig


def raise_interrupted(sig, _frame):
    raise Interrupted(sig)


def catch_termination():
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, raise_interrupted)


def cmd_timebox(args):
    if not args.cmd:
        die("timebox needs a command after --")
    token = secrets.token_hex(16)
    env = dict(os.environ, TIMEBOX_TOKEN=token)
    out = open(args.stdout, "wb") if args.stdout else None
    err = open(args.stderr, "wb") if args.stderr else None
    try:
        p = subprocess.Popen(args.cmd, cwd=args.cwd, env=env, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=out, stderr=err)
    except OSError as e:
        die("cannot start %s: %s" % (args.cmd[0], e))
    code = None
    catch_termination()
    try:
        code = p.wait(timeout=args.seconds)
    except Interrupted as e:
        code = 128 + e.sig
    except subprocess.TimeoutExpired:
        code = 124
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except OSError:
            pass
        if not wait_gone(lambda: group_alive(p.pid), 2):
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
        if p.poll() is None:
            p.kill()
            p.wait()
        left = token_pids(token)
        kill_all(left, signal.SIGTERM)
        if left and not wait_gone(lambda: bool(token_pids(token)), 2):
            kill_all(token_pids(token), signal.SIGKILL)
            wait_gone(lambda: bool(token_pids(token)), 2)
        for fh in (out, err):
            if fh:
                fh.close()
    return code if code >= 0 else 128 - code


def build_parser():
    ap = argparse.ArgumentParser(prog="diff-metrics", description=__doc__)
    sub = ap.add_subparsers(dest="verb")
    sub.required = True

    def target(p):
        g = p.add_mutually_exclusive_group()
        g.add_argument("--worktree", action="store_true")
        g.add_argument("--index", action="store_true")
        g.add_argument("--head", metavar="REV")

    p = sub.add_parser("diff")
    p.add_argument("--repo")
    p.add_argument("--base", required=True)
    target(p)
    p.add_argument("--binary", action="store_true")
    p.set_defaults(fn=cmd_diff)
    p = sub.add_parser("measure")
    p.add_argument("--diff", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--repo")
    p.add_argument("--base")
    target(p)
    p.add_argument("--coverage")
    p.add_argument("--coverage-langs", help="comma-separated languages the repo's coverage tool covers")
    p.set_defaults(fn=cmd_measure)
    p = sub.add_parser("bundle")
    p.add_argument("--metrics", required=True)
    p.add_argument("--diff", required=True)
    p.add_argument("--dir", required=True)
    p.set_defaults(fn=cmd_bundle)
    p = sub.add_parser("filter-lint")
    p.add_argument("--metrics", required=True)
    p.set_defaults(fn=cmd_filter_lint)
    p = sub.add_parser("snapshot")
    p.add_argument("--repo")
    p.add_argument("--index-dir", required=True)
    p.set_defaults(fn=cmd_snapshot)
    p = sub.add_parser("fingerprint")
    p.add_argument("--repo")
    p.set_defaults(fn=cmd_fingerprint)
    p = sub.add_parser("dirty")
    p.add_argument("--repo")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_dirty)
    p = sub.add_parser("commit-set")
    p.add_argument("--repo")
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)
    p.add_argument("--dirty", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_commit_set)
    p = sub.add_parser("timebox")
    p.add_argument("--seconds", type=float, required=True)
    p.add_argument("--stdout")
    p.add_argument("--stderr")
    p.add_argument("--cwd")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_timebox)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.verb == "timebox" and args.cmd and args.cmd[0] == "--":
        args.cmd = args.cmd[1:]
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
