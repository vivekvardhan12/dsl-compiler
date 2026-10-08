# Viva and Interview Questions

Questions an examiner or interviewer is likely to ask about this project,
with short answers you can explain in your own words. Each answer points to
the file where you can show it.

---

## A. Project basics

**1. What does your project do?**
It's a compiler for a small data analysis language. You write commands like
`filter marks > 60`; it checks them, optimizes them, translates them to
Python/pandas code and runs it. *(Demo: `python src/main.py examples/analysis.dsl --all`)*

**2. What is a DSL?**
A Domain-Specific Language: a small language made for one kind of task
(SQL for databases, HTML for web pages, regex for text patterns). Ours is for
simple data analysis. The opposite is a general-purpose language like C or Python.

**3. Is it a compiler or an interpreter? Why?**
A compiler. It *translates* the DSL into another language (Python) and saves
the result in `output/`; it doesn't execute the DSL itself. The output can be
read, shared and run without the compiler. (Our driver then runs that output
for convenience, the way `gcc` + `./a.out` would.)

**4. What is the source language and the target language?**
Source: our DSL. Target: Python using the pandas library.

**5. Why Python and not C?**
The target is pandas, so generating and testing Python is natural, and the
effort goes into the compiler phases rather than low-level string and memory
handling. The phases themselves are written by hand, so nothing is hidden.

**6. What are the phases of your compiler?**
Lexical analysis → syntax analysis → semantic analysis → optimization →
code generation, plus a driver that connects them. *(`src/main.py`, `CompilerDriver.compile`)*

---

## B. Lexical analysis (`lexer.py`)

**7. What does the lexer do?**
Turns raw text into tokens - the "words" of the language - each with a type,
value, line and column. Whitespace and comments are discarded.

**8. What is a token, a lexeme and a pattern?**
Lexeme: the actual text (`marks`). Token: its category (`IDENT`). Pattern:
the rule that matches it (a letter, then letters/digits/underscores).

**9. What is maximal munch?**
Always take the longest possible token. When the lexer sees `>` it peeks at
the next character; if it's `=`, the token is `>=`, not `>` followed by `=`.
*(`_read_operator`)*

**10. How do you tell keywords from identifiers?**
Read the whole word, then look it up in the `KEYWORDS` table. Found →
keyword; not found → identifier. *(`tokens.py`, `_read_word`)*

**11. Give an example of a lexical error.**
`filter marks @ 60` - `@` isn't part of the language. Also an unterminated
string or a lone `=`.

**12. Time complexity of the lexer?**
O(n) for n characters - each character is examined a constant number of times.

---

## C. Syntax analysis (`parser.py`)

**13. What does the parser do?**
Checks that tokens appear in an order the grammar allows, and builds an
Abstract Syntax Tree.

**14. Show your grammar.** See `docs/language-reference.md` section 2 (EBNF).

**15. Which parsing technique did you use?**
Recursive descent: a top-down parser with one method per grammar rule.

**16. Is your grammar LL(1)? Why?**
Yes. Every statement starts with a different keyword, so one token of
lookahead always chooses the rule, and no rule needs backtracking.
LL(1) = Left-to-right scan, Leftmost derivation, 1 lookahead token.

**17. Top-down vs bottom-up parsing?**
Top-down (LL, recursive descent) starts from the start symbol and expands
rules to match the input. Bottom-up (LR, SLR, LALR - used by yacc/bison)
starts from the tokens and reduces them to the start symbol. Bottom-up handles
more grammars; top-down is easier to write by hand.

**18. Parse tree vs AST?**
A parse tree keeps every token, including brackets and newlines. An AST keeps
only the meaning: `print avg(marks)` becomes `PrintNode(function="avg", column="marks")`.

**19. Give an example of a syntax error.**
`filter > 60` - every word is valid, but a column name must follow `filter`.

**20. What happens after the first syntax error?**
Compilation stops. Real compilers use *panic-mode recovery* - skip to the
next statement boundary (here, NEWLINE) and continue - to report several
errors at once. That's listed as future work.

---

## D. Semantic analysis (`semantic.py`)

**21. Why do you need semantic analysis if the parser already checks the program?**
The parser checks *form*, not *meaning*. `filter salary > 50` is perfectly
grammatical but wrong if the CSV has no `salary` column.

**22. What is your symbol table?**
A dictionary from each column of the *current* table to its type
(`number`/`text`). `load` creates it; `select` replaces it with a smaller one.

**23. How do you know the column types without declarations?**
Type inference: at compile time we read the CSV; if every non-empty value in
a column parses as a number, the column is `number`, otherwise `text`.

**24. How is `select` like variable scope?**
After `select name, marks`, the other columns stop existing - like a local
variable going out of scope. Using them afterwards is an error.
*(`SymbolTable.keep_only`)*

**25. Static vs dynamic checking?**
Static: before the program runs (our semantic phase). Dynamic: while it
runs. Without our static checks, pandas would crash halfway with a `KeyError`.

**26. Errors vs warnings?**
Errors make the program invalid and stop compilation. Warnings point out
probable mistakes (a program with no output) but still compile.

---

## E. Optimization (`optimizer.py`)

**27. What optimizations did you implement?**
Dead code elimination, filter (predicate) pushdown, filter merging,
redundant sort removal and redundant select removal.

**28. What's the golden rule of optimization?**
The optimized program must produce exactly the same output. We test this
directly: 7 programs are run with and without optimization and their outputs
compared. *(`test_optimized_output_matches_original`)*

**29. How does dead code elimination work?**
Backward liveness analysis: walk the program from the bottom with a flag
"is the table needed?". Outputs set it; `load` clears it. Any transform found
while it's off is dead.

**30. What are barriers and blocks?**
Barriers (`load`, `show`, `print`, `plot`) observe or replace the table, so
code may never move across them. Between them are blocks of pure transforms -
like basic blocks - where reordering is safe.

**31. Why is moving a filter before a `select` safe?**
A `select` only removes columns, so any column available after it was also
available before it. Filtering earlier means `select` and `sort` handle
fewer rows.

**32. Machine-independent vs machine-dependent optimization?**
Ours is machine-independent - it works on the AST. Machine-dependent
optimizations (register allocation, instruction scheduling) work on the
final machine code.

---

## F. Code generation (`codegen.py`)

**33. How does code generation work?**
Syntax-directed translation: each AST node type has a template returning
Python lines. The working table is always the variable `df`.

**34. How does `filter` become pandas code?**
`df = df[df['marks'] > 60]`. `df['marks'] > 60` produces a True/False *mask*
per row, and `df[mask]` keeps the True rows.

**35. How did you prevent code injection?**
All strings are written with `repr()`, which escapes them. A filter value
like `x'); print('HACKED'); ('` stays a plain string. There's a test for it.
It's the same class of bug as SQL injection.

---

## G. Engineering

**36. How did you test the project?**
170 pytest tests: unit tests per phase, integration tests of the whole
pipeline, equivalence tests for the optimizer, and smoke tests in CI.
99% branch coverage, with a 95% minimum enforced.

**37. What is code coverage? Line vs branch?**
The share of code executed by tests. Line coverage asks "did this line run?";
branch coverage also asks "did each `if` go both ways?" We use branch coverage.

**38. What is CI?**
Continuous Integration: GitHub Actions runs all tests automatically on every
push, on Linux and Windows with two Python versions.

**39. Which design principles did you follow?**
Single Responsibility (one phase per module), Open/Closed (dispatch tables:
new commands add entries, not edits), polymorphism (`DSLError` subclasses),
immutability (the optimizer returns a new AST).

**40. What would you add next?**
`group by`, `and`/`or` in filters, computed columns, panic-mode error
recovery, exact error positions for semantic errors, and type inference
from a sample for very large files.
