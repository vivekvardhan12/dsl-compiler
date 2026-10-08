# parser_error.dsl - every word is valid, but the ORDER is wrong.
# The lexer accepts this file; the parser rejects it.
load "examples/students.csv"
filter > 60
show
