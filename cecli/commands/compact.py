from .utils.base_command import BaseCommand


class CompactCommand(BaseCommand):
    NORM_NAME = "compact"
    DESCRIPTION = "Force compaction of the chat history context"

    @classmethod
    async def execute(cls, io, coder, args, **kwargs):
        await coder.compact_context_if_needed(force=True)

    @classmethod
    def get_help(cls) -> str:
        return "Force compaction of the chat history context."
