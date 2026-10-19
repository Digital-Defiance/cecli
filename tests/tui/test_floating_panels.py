import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, HorizontalScroll, Vertical
from textual.widgets import Static

from cecli.tui.widgets.floating_panels import (
    FloatingPanels,
    StatusItem,
    StatusItemClicked,
    StatusRow,
)
from cecli.tui.widgets.thin_scrollbar import ThinScrollBarRenderer


class FakeSkill:
    def __init__(self, name):
        self.name = name


class FakeSkills:
    def __init__(self):
        self._loaded_skills = {"pdf"}
        self.names = ["pdf", "docx", "spark"]

    def find_skills(self):
        return [FakeSkill(name) for name in self.names]


class FakeServer:
    def __init__(self, name, connected):
        self.name = name
        self.is_connected = connected


class FakeMcp:
    def __init__(self):
        self.servers = [FakeServer("local", True), FakeServer("github", False)]


class FakeCoder:
    registered_servers = {"included": set(), "excluded": set()}

    def __init__(self):
        self.skills_manager = FakeSkills()
        self.mcp_manager = FakeMcp()


class _PanelApp(App):
    CSS = """
    #input-row { height: auto; width: 100%; align-vertical: top; }
    #input-container { height: 5; width: 1fr; }
    #key-hints { height: 1; margin: 0 0 1 0; }
    """

    BINDINGS = [Binding("alt+p", "toggle_floating_panels", "Toggle panels", show=False)]

    def __init__(self):
        super().__init__()
        self.worker = SimpleNamespace(coder=FakeCoder())

    def compose(self) -> ComposeResult:
        with Horizontal(id="input-row"):
            with Vertical(id="input-column"):
                yield Static("input", id="input-container")
                yield Static("hints", id="key-hints")
            with Vertical(id="extensions-column"):
                yield FloatingPanels(id="floating-panels")
                yield Static("alt+p to toggle", id="extensions-hint")

    def action_toggle_floating_panels(self):
        self.query_one(FloatingPanels).toggle_visible()


def _row_text(panels: FloatingPanels, row_id: str) -> str:
    row = panels.query_one(f"#{row_id}", StatusRow)
    return " ".join(str(item.render()) for item in row.query(StatusItem))


async def _run_panel_checks():
    app = _PanelApp()
    async with app.run_test(size=(100, 40)) as pilot:
        panels = app.query_one("#floating-panels", FloatingPanels)
        input_container = app.query_one("#input-container")
        extensions_column = app.query_one("#extensions-column")
        input_column = app.query_one("#input-column")
        panels.refresh_data()
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        visible_input_width = input_container.region.width

        assert panels.border_title == "extensions"
        assert panels.region.x >= input_container.region.right
        assert panels.region.bottom == input_container.region.bottom
        assert panels.region.height == input_container.region.height

        labels = [str(label.render()) for label in panels.query(".status-label")]
        assert labels == ["Subagents:", "Skills:", "Servers:"]

        assert _row_text(panels, "subagents-row") == "● worker ○ tester"
        assert _row_text(panels, "skills-row") == "● pdf ○ docx ○ spark"
        assert _row_text(panels, "servers-row") == "● local ○ github"

        captured = []
        panels._run_coder_command = lambda category, name, active: captured.append(
            (category, name, active)
        )
        skill_items = list(panels.query_one("#skills-row", StatusRow).query(StatusItem))
        await pilot.click(skill_items[0])
        await pilot.pause()
        await pilot.click(skill_items[1])
        await pilot.pause()
        assert captured == [("skills", "pdf", True), ("skills", "docx", False)]

        panels.on_status_item_clicked(StatusItemClicked("subagents", "worker", False))
        panels.on_status_item_clicked(StatusItemClicked("servers", "github", False))
        assert captured[-2:] == [
            ("subagents", "worker", False),
            ("servers", "github", False),
        ]

        assert panels._command_class("subagents", False).__name__ == "SpawnAgentCommand"
        assert panels._command_class("skills", True).__name__ == "RemoveSkillCommand"
        assert panels._command_class("skills", False).__name__ == "LoadSkillCommand"
        assert panels._command_class("servers", True).__name__ == "RemoveMcpCommand"
        assert panels._command_class("servers", False).__name__ == "LoadMcpCommand"

        panels._set_row("#skills-row", [("z", True), ("a", True), ("b", False)])
        await pilot.pause()
        assert _row_text(panels, "skills-row") == "● a ● z ○ b"

        panels._set_row("#skills-row", [(f"skill-{i}", True) for i in range(20)])
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        scroll = panels.query_one(".status-scroll", HorizontalScroll)
        assert scroll.max_scroll_x > 0
        assert scroll.styles.scrollbar_visibility == "hidden"
        assert scroll.horizontal_scrollbar.renderer is ThinScrollBarRenderer
        assert "skill-19" in _row_text(panels, "skills-row")
        assert panels.region.height == input_container.region.height

        input_container.styles.height = 8
        await pilot.pause()
        await asyncio.sleep(0.35)
        await pilot.pause()
        assert panels.region.height == 8
        assert input_column.region.height == 10

        await pilot.press("alt+p")
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()
        assert extensions_column.display is False
        assert input_container.region.width > visible_input_width

        await pilot.press("alt+p")
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()
        assert extensions_column.display is True
        assert input_container.region.width == visible_input_width


def test_floating_panels_layout_scroll_and_toggle():
    agent_service = SimpleNamespace(
        sub_agents={"u1": SimpleNamespace(name="worker")},
        foreground_uuid="u1",
        foreground_coder=None,
    )
    with (
        patch(
            "cecli.helpers.agents.service.AgentService.get_instance",
            return_value=agent_service,
        ),
        patch(
            "cecli.helpers.agents.service.AgentService.get_registry",
            return_value={"tester": None, "worker": None},
        ),
    ):
        asyncio.run(_run_panel_checks())


def test_floating_panels_key_registration():
    from cecli.tui.app import TUI

    tui = object.__new__(TUI)
    tui.args = SimpleNamespace(tui_config=None)
    config = tui._get_config()

    assert config["key_bindings"]["panels"] == "alt+p"
    assert hasattr(TUI, "action_toggle_floating_panels")
