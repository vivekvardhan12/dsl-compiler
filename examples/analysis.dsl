# analysis.dsl - sample program written in our Data Analysis DSL
# Lines starting with '#' are comments; the compiler will ignore them.

load "examples/students.csv"
filter marks > 60
select name, city, marks
sort marks desc
show
print avg(marks)
print count(name)