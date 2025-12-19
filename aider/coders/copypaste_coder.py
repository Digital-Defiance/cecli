import hashlib
import json
import math
import time
import uuid

from aider.llm import litellm
from aider.exceptions import LiteLLMExceptions

from .base_coder import Coder


class CopyPasteCoder(Coder):
    """Coder implementation that performs clipboard-driven interactions."""

    async def send(self, messages, model=None, functions=None, tools=None):
        model = model or self.main_model

        if not getattr(model, "copy_paste_instead_of_api", False):
            async for chunk in super().send(
                messages, model=model, functions=functions, tools=tools
            ):
                yield chunk
            return

        if functions:
            self.io.tool_warning("copy/paste mode ignores function call requests.")
        if tools:
            self.io.tool_warning("copy/paste mode ignores tool call requests.")

        self.io.reset_streaming_response()

        self.partial_response_content = ""

        try:
            hash_object, completion = self.copy_paste_completion(messages, model)
            self.chat_completion_call_hashes.append(hash_object.hexdigest())
            self.show_send_output(completion)
            self.calculate_and_show_tokens_and_cost(messages, completion)
        finally:
            self.preprocess_response()

            if self.partial_response_content:
                self.io.ai_output(self.partial_response_content)

    def copy_paste_completion(self, messages, model):
        try:
            from aider import copypaste
        except ImportError:  # pragma: no cover - import error path
            self.io.tool_error("copy/paste mode requires the pyperclip package.")
            self.io.tool_output("Install it with: pip install pyperclip")
            raise

        def content_to_text(content):
            if not content:
                return ""
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                    elif isinstance(part, str):
                        parts.append(part)
                return "".join(parts)
            if isinstance(content, dict):
                text = content.get("text")
                if isinstance(text, str):
                    return text
                return ""
            return str(content)

        lines = []
        for message in messages:
            text_content = content_to_text(message.get("content"))
            if not text_content:
                continue
            role = message.get("role")
            if role:
                lines.append(f"{role.upper()}:\n{text_content}")
            else:
                lines.append(text_content)

        prompt_text = "\n\n".join(lines).strip()

        try:
            copypaste.copy_to_clipboard(prompt_text)
        except copypaste.ClipboardError as err:  # pragma: no cover - clipboard error path
            self.io.tool_error(f"Unable to copy prompt to clipboard: {err}")
            raise

        self.io.tool_output("Request copied to clipboard.")
        self.io.tool_output("Paste it into your LLM interface, then copy the reply back.")
        self.io.tool_output("Waiting for clipboard updates (Ctrl+C to cancel)...")

        try:
            last_value = copypaste.read_clipboard()
        except copypaste.ClipboardError as err:  # pragma: no cover - clipboard error path
            self.io.tool_error(f"Unable to read clipboard: {err}")
            raise

        try:
            response_text = copypaste.wait_for_clipboard_change(initial=last_value)
        except copypaste.ClipboardError as err:  # pragma: no cover - clipboard error path
            self.io.tool_error(f"Unable to read clipboard: {err}")
            raise

        # Estimate tokens locally using the model's tokenizer; fallback to heuristic.
        def _safe_token_count(text):
            if not text:
                return 0
            try:
                count = model.token_count(text)
                if isinstance(count, int) and count >= 0:
                    return count
            except Exception as ex:
                # Try to map known LiteLLM exceptions to user-friendly messages, then fallback.
                try:
                    ex_info = LiteLLMExceptions().get_ex_info(ex)
                    if ex_info and ex_info.description:
                        self.io.tool_warning(
                            f"Token count failed: {ex_info.description} Falling back to heuristic."
                        )
                except Exception:
                    # Avoid masking the original issue during error mapping.
                    pass
            return int(math.ceil(len(text) / 4))

        prompt_tokens = _safe_token_count(prompt_text)
        completion_tokens = _safe_token_count(response_text)
        total_tokens = prompt_tokens + completion_tokens

        completion = litellm.ModelResponse(
            id=f"chatcmpl-{uuid.uuid4()}",
            choices=[
                litellm.Choices(
                    index=0,
                    finish_reason="stop",
                    message=litellm.Message(role="assistant", content=response_text),
                )
            ],
            created=int(time.time()),
            model=model.name,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        )

        kwargs = dict(model=model.name, messages=messages, stream=False)
        hash_object = hashlib.sha1(json.dumps(kwargs, sort_keys=True).encode())

        return hash_object, completion
