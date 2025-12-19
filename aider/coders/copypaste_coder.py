import hashlib
import json
import time
import uuid

from aider.llm import litellm

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

        self.got_reasoning_content = False
        self.ended_reasoning_content = False

        self._streaming_buffer_length = 0
        self.io.reset_streaming_response()

        self.partial_response_content = ""
        self.partial_response_reasoning_content = ""
        self.partial_response_chunks = []
        self.partial_response_tool_calls = []
        self.partial_response_function_call = dict()

        completion = None

        try:
            hash_object, completion = self.copy_paste_completion(messages, model)
            self.chat_completion_call_hashes.append(hash_object.hexdigest())
            self.show_send_output(completion)
            self.calculate_and_show_tokens_and_cost(messages, completion)
        finally:
            self.preprocess_response()

            if self.partial_response_content:
                self.io.ai_output(self.partial_response_content)
            elif self.partial_response_function_call:
                args = self.parse_partial_args()
                if args:
                    self.io.ai_output(json.dumps(args, indent=4))

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
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

        kwargs = dict(model=model.name, messages=messages, stream=False)
        hash_object = hashlib.sha1(json.dumps(kwargs, sort_keys=True).encode())

        return hash_object, completion
