# plot_demo.dsl - Hyderabad students report plus a bar chart of their marks.
load "examples/students.csv"
filter city == "Hyderabad"
select name, marks
sort marks desc
show
print max(marks)
plot bar name marks
