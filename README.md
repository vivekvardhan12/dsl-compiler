# Data Analysis DSL Compiler

A beginner-friendly compiler (Compiler Design course project) that translates
a small data-analysis language into Python/pandas code and runs it.

## Example

    load "examples/students.csv"
    filter marks > 60
    sort marks desc
    show

## Setup

    conda create -n dslc python=3.13 -y
    conda activate dslc
    pip install -r requirements.txt

## Progress

- [x] Step 0 - Project setup
- [x] Step 1 - Lexer (`python src/lexer.py examples/analysis.dsl`)
- [x] Step 2 - Parser (`python src/parser.py examples/analysis.dsl`)
- [ ] Step 3 - Semantic analysis
- [ ] Step 4 - Code generation
- [ ] Step 5 - Compiler driver (main.py)
- [ ] Step 6 - Optimizer
- [ ] Step 7 - Tests
- [ ] Step 8 - Documentation

## Run the tests

    pytest -v
