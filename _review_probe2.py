import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import tokenize

# Probe: does the tokenizer see >= inside a standalone docstring as an OP token?
# Two sub-cases:
#   A) docstring only (no code after)
#   B) docstring as a function body doc with real code after

case_a = '"""Return True if x >= 10."""\n'
case_b = '"""Return True if x >= 10."""\nreturn x >= 10\n'
case_c = 'def f(x):\n    """Return True if x >= 10."""\n    return x >= 10\n'

for label, src in [("case_a standalone", case_a), ("case_b docstr+code", case_b), ("case_c func docstr+code", case_c)]:
    print(f"\n=== {label} ===")
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
        for tok in toks:
            tt, ts, tstart, tend, tline = tok
            tname = tokenize.tok_name[tt]
            if ts in (">=", ">", "==", "!=", "+", "-"):
                print(f"  MUTABLE  type={tname:<10} string={ts!r} start={tstart}")
            elif tt in (tokenize.STRING, tokenize.COMMENT, tokenize.OP):
                print(f"  relevant type={tname:<10} string={ts[:40]!r} start={tstart}")
    except tokenize.TokenError as e:
        print(f"  TokenError: {e}")
