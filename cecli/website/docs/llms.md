---
title: Connecting to LLMs
nav_order: 55
has_children: true
description: cecli can connect to most LLMs for AI pair programming.
---

## Recommended models
{: .no_toc }

cecli works best with these models, which are skilled at editing code:

- [Gemini 3+](/docs/llms/gemini.html)
- [DeepSeek V4+](/docs/llms/deepseek.html)
- [Claude 4+](/docs/llms/anthropic.html)
- [GPT 5+](/docs/llms/openai.html)


## Free models
{: .no_toc }

cecli works with a number of **free** API providers:

- [OpenRouter offers free access to many models](https://openrouter.ai/models/?q=free), with limitations on daily usage.

## Local models
{: .no_toc }

cecli can also work with local models, for example using [Ollama](/docs/llms/ollama.html).
It can also access
local models that provide an
[Open AI compatible API](/docs/llms/openai-compat.html).

## Use a capable model
{: .no_toc }

Be aware that cecli may not work well with less capable models.
If you see the model returning code, but cecli isn't able to edit your files
and commit the changes...
this is usually because the model isn't capable of properly
returning "code edits".
Models weaker than GPT 4o may have problems working well with cecli.

