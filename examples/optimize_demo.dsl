# optimize_demo.dsl - deliberately wasteful, to show what the optimizer does.
# Compare:  python src/main.py examples/optimize_demo.dsl --opt --code
#     and:  python src/main.py examples/optimize_demo.dsl --no-optimize --code

load "examples/students.csv"
sort name                    # redundant: re-sorted by marks below
select name, city, marks     # redundant: the later select picks the final columns
filter marks > 60            # pushed to the front, then merged...
sort marks desc
filter city != "Mumbai"      # ...with this filter into ONE filter
select name, marks
show
print avg(marks)
sort name                    # dead code: nothing is shown after it
