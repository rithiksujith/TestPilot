import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from backend.mutations.engine import _find_mutable_tokens

cases = {
    "inline comment":      "x = 1  # if x >= 10: skip\n",
    "standalone comment":  "# x >= 10 means something\n",
    "string literal":      'msg = "value >= 10"\n',
    "fstring":             'f = f"result >= 0"\n',
    "docstring":           '"""Return True if x >= 10."""\nx = x >= 10\n',
    "real code+comment":   "if x >= 10:  # also >= 5?\n",
    "real code only":      "if x >= 10:\n    return x + 1\n",
    "neq in string":       'msg = "x != 0 means nonzero"\n',
    "eq in string":        'label = "x == y"\n',
    "plus in comment":     "# total = a + b\n",
}

for label, src in cases.items():
    toks = _find_mutable_tokens(src)
    pairs = [(t[3], t[4]) for t in toks]
    print(f"{label:<30}: {len(toks)} token(s) {pairs}")
