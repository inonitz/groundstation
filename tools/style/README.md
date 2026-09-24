# tools/style

Layout helpers for harden2's house style (lines < 90, no one-line compound statements, blank lines).
Each proves the program is unchanged (AST compare) before it writes a file.

| file | use |
|---|---|
| layout.py | run from the harden2 root: fixes flake8 E701/E704 and E30x in every file |
| refill.py | `python3 refill.py <file> '<first line of a docstring>'`: reflows that ONE docstring to 89 |
| check_wrap.py | compares files with a backup tree (BACKUP inside) and lists lines > 89 |

Check: `python3 -m flake8 --isolated --select=E30,E501,E70,E731 --max-line-length=89 --exclude=__pycache__ .`
