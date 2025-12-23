# Aider benchmark harness

Before `cecli` was born, the old `aider` used benchmarks to quantitatively
measure how well it works with various LLMs.

This directory holds the harness and tools needed to run the benchmarking suite.

## Background

The benchmark was based on the [Exercism](https://github.com/exercism/python)
coding exercises. This benchmark evaluates how effectively aider and LLMs can
translate a natural language coding request into executable code saved into
files that pass unit tests. It provides an end-to-end evaluation of not just the
LLM's coding ability, but also its capacity to _edit existing code_ and _format
those code edits_ so that aider can save the edits to the local source files.

See
[this writeup for a longer discussion about the benchmark](https://aider.chat/2024/12/21/polyglot.html).

The benchmark is intended to be run _inside a docker container_. This is because
the benchmarking harness will be taking code written by an LLM and executing it
without any human review or supervision! The LLM could generate dangerous python
that harms your system, like this: `import os; os.system("sudo rm -rf /")`.
Running inside a docker container helps limit the damage that could be done.

## Usage

There are 3 main tasks involved in benchmarking:

1. Install and setup.

2. Run the benchmark.

3. Analysis.

### Setup

These steps only need to be done once.

```
ORG=Aider-AI
REPO=aider
# Clone the main repo
git clone https://github.com/$ORG/$REPO.git

# Create the scratch dir to hold benchmarking results inside the main repo:
cd $REPO
mkdir tmp.benchmarks

# Clone the repo with the exercises
git clone https://github.com/$ORG/polyglot-benchmark tmp.benchmarks/polyglot-benchmark

# Build the docker container
./benchmark/docker_build.sh
```

### Running the benchmarks

Launch the docker container and run the benchmark inside it:

```
# Launch the docker container
./benchmark/docker.sh

# Inside the container, install aider as a development build.
# This way you're running the code that you cloned above, including any local changes.
# TODO: this step should be included in the Dockerfile
pip install -e .[dev]

# Run the benchmark:
./benchmark/benchmark.py a-helpful-name-for-this-run --model gpt-3.5-turbo --edit-format whole --threads 10 --exercises-dir polyglot-benchmark
```

The above will create a folder
`tmp.benchmarks/YYYY-MM-DD-HH-MM-SS--a-helpful-name-for-this-run` with
benchmarking results. Run like this, the script will run all the exercises in a
random order.

You can run `./benchmark/benchmark.py --help` for a list of all the arguments,
but here are the most useful to keep in mind:

- `--model` is the name of the model, same as you would pass directly to
  `aider`.
- `--edit-format` is the name of the edit format, same as you would pass
  directly to `aider`. When working with an experimental LLM, I recommend
  starting with `whole`
- `--threads` specifies how many exercises to benchmark in parallel. Start with
  a single thread if you are working out the kinks on your benchmarking setup or
  working with a new model, etc. Once you are getting reliable results, you can
  speed up the process by running with more threads. 10 works well against the
  OpenAI APIs.
- `--num-tests` specifies how many of the tests to run before stopping. This is
  another way to start gently as you debug your benchmarking setup.
- `--keywords` filters the tests to run to only the ones whose name match the
  supplied argument (similar to `pytest -k xxxx`).
- `--read-model-settings=<filename.yml>` specify model settings, see here:
  https://aider.chat/docs/config/adv-model-settings.html#model-settings
- `--map-tokens` sets a token budget for the repo map sent with each request.
  Set `0` to disable the repo map. This lets you enable repo map usage for any
  model (e.g., `--map-tokens 1024`).

### Benchmark report

You can generate stats about any benchmark, including ones which are still
running. You don't need to run this inside the docker container, as it is just
collecting stats not executing unsafe python.

```
# Generate stats for a specific benchmarking directory
./benchmark/benchmark.py --stats tmp.benchmarks/YYYY-MM-DD-HH-MM-SS--a-helpful-name-for-this-run
```

The benchmark report is a yaml record with statistics about the run:

```yaml
- dirname: 2024-07-04-14-32-08--claude-3.5-sonnet-diff-continue
  test_cases: 225
  model: claude-3.5-sonnet
  edit_format: diff
  commit_hash: 35f21b5
  pass_rate_1: 57.1
  pass_rate_2: 77.4
  percent_cases_well_formed: 99.2
  error_outputs: 23
  num_malformed_responses: 4
  num_with_malformed_responses: 1
  user_asks: 2
  lazy_comments: 0
  syntax_errors: 1
  indentation_errors: 0
  exhausted_context_windows: 0
  test_timeouts: 1
  command: aider --sonnet
  date: 2024-07-04
  versions: 0.42.1-dev
  seconds_per_case: 17.6
  total_cost: 3.6346
```

The key statistics are the `pass_rate_#` entries, which report the percent of
the tasks which had all tests passing. There will be multiple of these pass rate
stats, depending on the value of the `--tries` parameter.

The yaml also includes all the settings which were in effect for the benchmark
run. It also reports the git hash of the repo at the time that the benchmark was
run, with `(dirty)` if there were uncommitted changes. It's good practice to
commit the repo before starting a benchmark run. This way the `model`,
`edit_format` and `commit_hash` should be enough to reliably reproduce any
benchmark run.

You can see examples of the benchmark report yaml in the
[aider leaderboard data files](https://github.com/$ORG/aider/blob/main/aider/website/_data/).

## Limitations, notes

- Contributions of benchmark results are welcome! Submit results by opening a PR
  with edits to the
  [aider leaderboard data files](https://github.com/$ORG/aider/blob/main/aider/website/_data/).
- These scripts are not intended for use by typical aider end users.
- Some of these tools are written as `bash` scripts, so it will be hard to use
  them on Windows.

## Enhancements

The `aider-ce` benchmark harness includes several enhancements over the original
`aider` benchmark:

- **YAML Metadata**: Exercises now use `cat.yaml` files for metadata, allowing
  for richer categorization and filtering.
- **Subset Filtering**: Use the `--sets` option to run specific groups of tests
  (e.g., `--sets core,strings`).
- **K-fold Evaluation Slicing**: The `--hash-re` option allows for deterministic
  slicing of the exercise set based on the exercise hash. This is useful for
  parallelizing runs or performing k-fold cross-validation.
  - `^0`: 1/16 of the set.
  - `^[01]`: 1/8 of the set.
  - `^[0-3]`: 1/4 of the set.
  - `^.{2}[4-7]`: Targets the 3rd character of the hash for more granular
    slicing.
