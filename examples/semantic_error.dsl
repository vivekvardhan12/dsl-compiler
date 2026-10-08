# semantic_error.dsl - perfect grammar, but the meaning is wrong.
# The lexer and parser accept this file; semantic analysis rejects it.
load "examples/students.csv"
select name, marks
filter mark > 60
show
