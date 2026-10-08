# Language Reference

The Data Analysis DSL is a line-based language: **one command per line**.
A program reads a CSV file into a *working table*, transforms that table step
by step, and prints results along the way.

---

## 1. Lexical structure (what the lexer accepts)

| Element | Rule | Examples |
|---|---|---|
| Keyword | One of the reserved words below, **case-insensitive** | `filter`, `FILTER`, `Sort` |
| Identifier (column name) | Letter or `_`, then letters, digits or `_`. **Case-sensitive** | `marks`, `total_marks2`, `_id` |
| Number | Digits, optionally `.` and more digits | `60`, `3.75` |
| String | Text in double quotes, on one line | `"students.csv"`, `"Hyderabad"` |
| Operator | `>` `<` `>=` `<=` `==` `!=` | |
| Punctuation | `,` `(` `)` | |
| Comment | `#` to the end of the line (except inside a string) | `# my note` |
| Whitespace | Spaces, tabs and blank lines are ignored | |

**Reserved words:** `load` `filter` `select` `sort` `show` `print` `plot`
`asc` `desc` `count` `sum` `avg` `min` `max`.
These cannot be used as column names.

**Not supported:** single `=` (use `==`), single `!` (use `!=`), negative
numbers, single-quoted strings, strings spanning several lines.

---

## 2. Grammar (EBNF)

```ebnf
program    ::= statement* EOF
statement  ::= ( load | filter | select | sort | show | print | plot ) NEWLINE

load       ::= LOAD STRING
filter     ::= FILTER IDENT comparison value
select     ::= SELECT IDENT ( COMMA IDENT )*
sort       ::= SORT IDENT [ ASC | DESC ]
show       ::= SHOW
print      ::= PRINT aggregate LPAREN IDENT RPAREN
plot       ::= PLOT IDENT IDENT IDENT

comparison ::= GT | LT | GE | LE | EQ | NE
value      ::= NUMBER | STRING
aggregate  ::= COUNT | SUM | AVG | MIN | MAX
```

How to read it: `*` = zero or more, `[ ]` = optional, `|` = or. UPPERCASE names
are tokens from the lexer; lowercase names are grammar rules. The first token
of every statement decides which rule applies, so the grammar is **LL(1)**.

---

## 3. Commands

### `load "file.csv"`
Reads a CSV file into the working table. The file must exist, end in `.csv`,
and have a header row without duplicate names. Paths are relative to the
folder you run the compiler from. A second `load` replaces the table.

```text
load "examples/students.csv"
```

### `filter column operator value`
Keeps only the rows where the condition is true.

```text
filter marks >= 60
filter city == "Hyderabad"
filter city != "Mumbai"
```

### `select column, column, ...`
Keeps only the listed columns, in the listed order. Columns not listed
**no longer exist** for later commands.

```text
select name, marks
```

### `sort column [asc | desc]`
Orders the rows by one column. `asc` (smallest first) is the default.
Rows with equal values may appear in any order, like SQL's `ORDER BY`.

```text
sort marks desc
sort name
```

### `show`
Prints the whole working table.

### `print function(column)`
Prints one summary value, labelled, e.g. `avg(marks) = 81.29`.

| Function | Meaning | Works on |
|---|---|---|
| `count` | Number of non-empty values | numbers and text |
| `sum` | Total | numbers only |
| `avg` | Average, rounded to 2 decimals | numbers only |
| `min` | Smallest (alphabetically first for text) | numbers and text |
| `max` | Largest (alphabetically last for text) | numbers and text |

### `plot kind x_column y_column`
Draws a chart, saves it as `output/<program>_plot_line<N>.png` and opens it.

| Kind | x-axis | y-axis |
|---|---|---|
| `bar` | any column | number column |
| `line` | any column | number column |
| `scatter` | number column | number column |

```text
plot bar name marks
```

---

## 4. Type rules (checked by semantic analysis)

Column types are **inferred** from the CSV when compiling: a column is
`number` if every non-empty value is numeric, otherwise `text`.

| Rule | Valid | Invalid |
|---|---|---|
| `load` must come before every other command | `load ...` then `show` | `show` as the first command |
| Columns must exist in the *current* table | `filter marks > 60` | `filter mark > 60` |
| `select` removes columns for later commands | `select name` then `sort name` | `select name` then `sort marks` |
| A column may appear only once in `select` | `select name, marks` | `select name, name` |
| Number columns compare with numbers | `filter marks > 60` | `filter marks > "60"` |
| Text columns compare with quoted text | `filter city == "Pune"` | `filter city == 5` |
| Text columns allow only `==` and `!=` | `filter city != "Pune"` | `filter city > "A"` |
| `sum` / `avg` need a number column | `print avg(marks)` | `print avg(name)` |
| `plot` y-axis must be a number column | `plot bar name marks` | `plot bar marks name` |
| `scatter` needs numbers on both axes | `plot scatter age marks` | `plot scatter name marks` |

A program with no `show`, `print` or `plot` compiles with a **warning**
(it would produce no output).

---

## 5. Translation to Python

| DSL | Generated pandas code |
|---|---|
| `load "f.csv"` | `df = pd.read_csv('f.csv')` |
| `filter marks > 60` | `df = df[df['marks'] > 60]` |
| two merged filters | `df = df[(df['marks'] > 60) & (df['city'] == 'Pune')]` |
| `select name, marks` | `df = df[['name', 'marks']]` |
| `sort marks desc` | `df = df.sort_values('marks', ascending=False)` |
| `show` | `print(df.to_string(index=False))` |
| `print avg(marks)` | `print('avg(marks)', '=', round(df['marks'].mean(), 2))` |
| `plot bar name marks` | `df.plot(kind='bar', x='name', y='marks', ...)` + save + show |

---

## 6. A complete example

```text
# Top Hyderabad students
load "examples/students.csv"
filter city == "Hyderabad"
filter marks > 60
select name, marks
sort marks desc
show
print count(name)
print max(marks)
plot bar name marks
```
