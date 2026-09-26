import sys, io, textwrap
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pathlib, tempfile

from backend.mutations.engine import generate_mutations

# Replicate the exact test case from TestStringsNotMutated::test_operator_inside_docstring_ignored
src_text = textwrap.dedent("""\
    def f(x):
        \"\"\"Return True if x >= 10.\"\"\"
        return x >= 10
""")

with tempfile.TemporaryDirectory() as td:
    p = pathlib.Path(td) / "source.py"
    p.write_text(src_text)
    mutations = generate_mutations(p)
    print(f"Mutations found: {len(mutations)}")
    for m in mutations:
        op = m.operator.encode("ascii", "replace").decode()
        print(f"  line={m.line_number} op={op} orig={m.original_line.strip()!r}")

# Result should be 1 mutation — only the real >= in return statement, NOT the docstring one
