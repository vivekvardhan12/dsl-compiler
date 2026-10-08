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

## Status

Under development. Compiler phases are being added one module at a time.
