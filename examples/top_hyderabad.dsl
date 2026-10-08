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
