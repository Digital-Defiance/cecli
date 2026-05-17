from cecli.tools.utils.base_tool import BaseTool


class Tool(BaseTool):
    NORM_NAME = "finished"
    TRACK_INVOCATIONS = False
    SCHEMA = {
        "type": "function",
        "function": {
            "name": "Finished",
            "description": (
                "Declare that we are done with every single sub goal and no further work is needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": (
                            "Optional summary of what was accomplished. "
                            "When called by a sub-agent, this summary is captured "
                            "and returned to the parent agent."
                        ),
                    },
                },
                "required": [],
            },
        },
    }

    @classmethod
    async def execute(cls, coder, **kwargs):
        """
        Mark that the current generation task needs no further effort.

        This gives the LLM explicit control over when it can stop looping
        """
        cls.clear_invocation_cache()

        if coder:
            coder.agent_finished = True

            # If this is a sub-agent, capture the summary for the parent
            summary = kwargs.get("summary", None)
            parent_uuid = coder.parent_uuid
            if parent_uuid:
                try:
                    from cecli.helpers.agents.service import AgentService

                    AgentService.mark_sub_agent_finished(
                        sub_coder_uuid=coder.uuid,
                        parent_uuid=parent_uuid,
                        summary=summary,
                    )
                except Exception:
                    pass

            if coder.files_edited_by_tools:
                _ = await coder.auto_commit(coder.files_edited_by_tools)
                coder.files_edited_by_tools = set()

            if summary:
                return f"Task Finished! Summary: {summary}"
            return "Task Finished!"

        # coder.io.tool_Error("Error: Could not mark agent task as finished")
        return "Error: Could not mark agent task as finished"
