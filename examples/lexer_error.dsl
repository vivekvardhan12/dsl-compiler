# lexer_error.dsl - a program with a deliberate mistake, to see the error message.
load "examples/students.csv"
filter marks @ 60
show
