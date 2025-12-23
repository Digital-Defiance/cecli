# Debug Plan

The benchmark script is failing because `Coder` has been converted to use
`async/await`, but `benchmark.py` is still synchronous.

## Symptom

`AttributeError: 'coroutine' object has no attribute 'ignore_mentions'` when
accessing properties of the result of `Coder.create()`.

## Diagnosis

1. `Coder.create()` is `async def` and returns a coroutine.
2. `benchmark.py` calls it as `coder = Coder.create(...)` without awaiting.
3. `coder.run()` is also `async def` and needs to be awaited.
4. `coder.apply_updates()` is also `async def` and needs to be awaited (used in
   replay mode).

## Plan

We need to bridge the synchronous benchmark runner with the async `Coder`.

1.  Modify `benchmark/benchmark.py`.
2.  Import `asyncio`.
3.  Wrap the coder creation and execution in an async function.
4.  Use `asyncio.run()` to execute that function within `run_test_real`.

The async function needs to handle:

- `coder = await Coder.create(...)`
- `response = await coder.run(...)`
- `await coder.apply_updates()`

## Files to Edit

- `benchmark/benchmark.py`
