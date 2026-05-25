---
title: Installation
has_children: true
nav_order: 20
description: Install bright-vision-core and run the CLI or HTTP server.
---

# Installation
{: .no_toc }

{% include bright-vision-notice.md %}

## Quick start

{% include get-started.md %}

Optional: [optional install steps](/docs/install/optional.html). Usage details for the shared engine: [Usage](/docs/usage.html) and [upstream usage](https://cecli.dev/docs/usage.html).

The upstream [cecli.dev install.sh](https://cecli.dev/install.sh) flow installs **Cecli**, not this package — use `pip install bright-vision-core` for Vision Core.

## One-liners (upstream Cecli)

These install **cecli** from [cecli.dev](https://cecli.dev/) (not `bright-vision-core`).
For Vision Core use `pip install bright-vision-core` above.
Based on [uv](https://docs.astral.sh/uv/getting-started/installation/).

#### Mac & Linux

Use curl to download the script and execute it with sh:

```bash
curl -LsSf https://cecli.dev/install.sh | sh
```

If your system doesn't have curl, you can use wget:

```bash
wget -qO- https://cecli.dev/install.sh | sh
```

#### Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://cecli.dev/install.ps1 | iex"
```


## Install with uv

Install **bright-vision-core** (includes `cecli` + `bright-vision-core-serve`) with uv:

```bash
python -m pip install uv  # If you need to install uv
uv tool install --force --python python3.12 --with pip bright-vision-core@latest
```

This will install uv using your existing python version 3.8-3.13,
and use it to pip install bright-vision-core.
If needed, 
uv will automatically install a separate python 3.12 to use with cecli.

Also see the
[docs on other methods for installing uv itself](https://docs.astral.sh/uv/getting-started/installation/).

## Install with pipx

Install with pipx:

```bash
python -m pip install pipx  # If you need to install pipx
pipx install bright-vision-core
```

Python 3.9–3.12 supported.

Also see the
[docs on other methods for installing pipx itself](https://pipx.pypa.io/stable/installation/).

## Other install methods

Other methods below; prefer **pip install bright-vision-core** for this package.

#### Install with pip

If you install with pip, you should consider
using a 
[virtual environment](https://docs.python.org/3/library/venv.html)
to keep cecli's dependencies separated.


Python 3.9–3.12:

```bash
python -m pip install -U --upgrade-strategy only-if-needed bright-vision-core
```

{% include python-m-cecli.md %}

#### Installing with package managers

Prefer **PyPI `bright-vision-core`** for this repo.
Third-party distro packages may target upstream cecli only.

## Next steps...

There are some [optional install steps](/docs/install/optional.html) you could consider.
See the [usage instructions](https://cecli.dev/docs/usage.html) to start coding with cecli.

