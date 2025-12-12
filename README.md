## Why `aider-ce`?

`aider-ce` (aka `cecli`, pronounced like "Cecily") is a community-driven fork of the [Aider](https://aider.chat/) AI pair programming tool.
Aider is a fantastic piece of software with a wonderful community but it has been painfully slow in receiving updates in the quickly evolving AI tooling space.

We aim to foster an open, collaborative ecosystem where new features, experiments, and improvements can be developed and shared rapidly. We believe in genuine FOSS principles and actively welcome contributors of all skill levels.

If you are looking for bleeding-edge features or want to get your hands dirty with the internals of an AI coding agent, here's your sign.
LLMs are a part of our lives from here on out so join us in learning about and crafting the future.

### Links

[Discord Chat](https://discord.gg/AX9ZEA7nJn) 🞄
[Changelog](https://github.com/dwash96/aider-ce/blob/main/CHANGELOG.md) 🞄
[Issue Queue](https://github.com/dwash96/aider-ce/issues)

## Documentation/Other Notes:

* [Agent Mode](https://github.com/dwash96/aider-ce/blob/main/aider/website/docs/config/agent-mode.md)
* [MCP Configuration](https://github.com/dwash96/aider-ce/blob/main/aider/website/docs/config/mcp.md)
* [Session Management](https://github.com/dwash96/aider-ce/blob/main/aider/website/docs/sessions.md)
* [Skills](https://github.com/dwash96/aider-ce/blob/main/aider/website/docs/config/skills.md)
* [Aider Original Documentation (still mostly applies)](https://aider.chat/)

You can see a selection of the enhancements and updates by comparing the help output:
```bash
aider --help > aider.help.txt
cecli --help > cecli.help.txt
diff aider.help.txt cecli.help.txt -uw --color
```

## Installation Instructions
This project can be installed using several methods:

### Package Installation
```bash
pip install aider-ce
```

or

```bash
uv pip install --native-tls aider-ce
```

The package exports an `aider-ce` command that accepts all of Aider's configuration options

### Tool Installation
```bash
uv tool install --native-tls --python python3.12 aider-ce
```

Use the tool installation so aider doesn't interfere with your development environment

## Configuration

The documentation above contains the full set of allowed configuration options
but I highly recommend using an `.aider.conf.yml` file. A good place to get started is:

```yaml
model: <model of your choice>
agent: true
analytics: false
auto-commits: true
auto-save: true
auto-load: false
cache-prompts: true
check-update: true
debug: false
enable-context-compaction: true
context-compaction-max-tokens: 64000
env-file: .aider.env
multiline: true
preserve-todo-list: true
show-model-warnings: true
use-enhanced-map: true
watch-files: false

agent-config:
  large_file_token_threshold: 12500
  skip_cli_confirmations: false

mcp-servers:
  mcpServers:
    context7:
      transport: http
      url: https://mcp.context7.com/mcp
```

Use the adjacent .aider.env file to store model api keys as environment variables, e.g:

```
ANTHROPIC_API_KEY="..."
GEMINI_API_KEY="..."
OPENAI_API_KEY="..."
OPENROUTER_API_KEY="..."
DEEPSEEK_API_KEY="..."
```

### Run Program

If you are in the directory with your .aider.conf.yml file, then simply running `aider-ce` or `cecli` will start the agent with your configuration. If you want additional sandboxing, we publish a docker container that can be ran as follows:

```bash
docker pull dustinwashington/aider-ce
docker run \
  -it \
  --user $(id -u):$(id -g) \
  --volume $(pwd):/app dustinwashington/aider-ce \
  --volume $(pwd)/.aider.conf.yml:/.aider.conf.yml \
  --volume $(pwd)/.aider.env:/.aider/.env \
  --config /app/.aider.conf.yml
```

This command will make sure all commands ran by the coding agent happen in context of the docker container to protect the host file system from any infamous agentic mishap

## Project Roadmap/Goals

The current priorities are to improve core capabilities and user experience of the Aider project

1. **Base Asynchronicity (aider-ce coroutine-experiment branch)**
  * [x] Refactor codebase to have the main loop run asynchronously
  * [x] Update test harness to work with new asynchronous methods

2. **Repo Map Accuracy** - [Discussion](https://github.com/dwash96/aider-ce/issues/45)
  * [x] [Bias page ranking toward active/editable files in repo map parsing](https://github.com/Aider-AI/aider/issues/2405)
  * [x] [Include import information in repo map for richer context](https://github.com/Aider-AI/aider/issues/2688)
  * [x] [Handle non-unique symbols that break down in large codebases](https://github.com/Aider-AI/aider/issues/2341)

3. **Context Discovery** - [Discussion](https://github.com/dwash96/aider-ce/issues/46)
  * [ ] Develop AST-based search capabilities
  * [ ] Enhance file search with ripgrep integration
  * [ ] Implement RAG (Retrieval-Augmented Generation) for better code retrieval
  * [ ] Build an explicit workflow and local tooling for internal discovery mechanisms

4. **Context Delivery** - [Discussion](https://github.com/dwash96/aider-ce/issues/47)
  * [ ] Use workflow for internal discovery to better target file snippets needed for specific tasks
  * [ ] Add support for partial files and code snippets in model completion messages

5. **TUI Experience** - [Discussion](https://github.com/dwash96/aider-ce/issues/48)
  * [ ] Add a full TUI (probably using textual) to have a visual interface competitive with the other coding agent terminal programs
  * [x] Re-integrate pretty output formatting
  * [ ] Implement a response area, a prompt area with current auto completion capabilities, and a helper area for management utility commands

6. **Agent Mode** - [Discussion](https://github.com/dwash96/aider-ce/issues/111)
  * [x] Renaming "navigator mode" to "agent mode" for simplicity
  * [x] Add an explicit "finished" internal tool
  * [x] Add a configuration json setting for agent mode to specify allowed local tools to use, tool call limits, etc.
  * [ ] Add a RAG tool for the model to ask questions about the codebase
  * [ ] Make the system prompts more aggressive about removing unneeded files/content from the context
  * [ ] Add a plugin-like system for allowing agent mode to use user-defined tools in simple python files
  * [x] Add a dynamic tool discovery tool to allow the system to have only the tools it needs in context

### All Contributors (Both Aider Main and Aider-CE)

<table>
<tbody>
<tr>
<td><a href="https://github.com/paul-gauthier">@paul-gauthier</a></td>
<td><a href="https://github.com/dwash96">@dwash96</a></td>
<td><a href="https://github.com/tekacs">@tekacs</a></td>
<td><a href="https://github.com/ei-grad">@ei-grad</a></td>
</tr>
<tr>
<td><a href="https://github.com/joshuavial">@joshuavial</a></td>
<td><a href="https://github.com/chr15m">@chr15m</a></td>
<td><a href="https://github.com/fry69">@fry69</a></td>
<td><a href="https://github.com/quinlanjager">@quinlanjager</a></td>
</tr>
<tr>
<td><a href="https://github.com/caseymcc">@caseymcc</a></td>
<td><a href="https://github.com/shladnik">@shladnik</a></td>
<td><a href="https://github.com/itlackey">@itlackey</a></td>
<td><a href="https://github.com/tomjuggler">@tomjuggler</a></td>
</tr>
<tr>
<td><a href="https://github.com/szmania">@szmania</a></td>
<td><a href="https://github.com/vk4s">@vk4s</a></td>
<td><a href="https://github.com/titusz">@titusz</a></td>
<td><a href="https://github.com/daniel-vainsencher">@daniel-vainsencher</a></td>
</tr>
<tr>
<td><a href="https://github.com/bphd">@bphd</a></td>
<td><a href="https://github.com/akaihola">@akaihola</a></td>
<td><a href="https://github.com/jalammar">@jalammar</a></td>
<td><a href="https://github.com/schpet">@schpet</a></td>
</tr>
<tr>
<td><a href="https://github.com/iamFIREcracker">@iamFIREcracker</a></td>
<td><a href="https://github.com/ErichBSchulz">@ErichBSchulz</a></td>
<td><a href="https://github.com/KennyDizi">@KennyDizi</a></td>
<td><a href="https://github.com/ivanfioravanti">@ivanfioravanti</a></td>
</tr>
<tr>
<td><a href="https://github.com/mdeweerd">@mdeweerd</a></td>
<td><a href="https://github.com/fahmad91">@fahmad91</a></td>
<td><a href="https://github.com/itsmeknt">@itsmeknt</a></td>
<td><a href="https://github.com/cheahjs">@cheahjs</a></td>
</tr>
<tr>
<td><a href="https://github.com/youknow04">@youknow04</a></td>
<td><a href="https://github.com/pjcreath">@pjcreath</a></td>
<td><a href="https://github.com/pcamp">@pcamp</a></td>
<td><a href="https://github.com/miradnanali">@miradnanali</a></td>
</tr>
<tr>
<td><a href="https://github.com/o-nix">@o-nix</a></td>
<td><a href="https://github.com/jpshackelford">@jpshackelford</a></td>
<td><a href="https://github.com/johbo">@johbo</a></td>
<td><a href="https://github.com/jamwil">@jamwil</a></td>
</tr>
<tr>
<td><a href="https://github.com/claui">@claui</a></td>
<td><a href="https://github.com/codeofdusk">@codeofdusk</a></td>
<td><a href="https://github.com/Taik">@Taik</a></td>
<td><a href="https://github.com/Hambaobao">@Hambaobao</a></td>
</tr>
<tr>
<td><a href="https://github.com/therealmarv">@therealmarv</a></td>
<td><a href="https://github.com/muravvv">@muravvv</a></td>
<td><a href="https://github.com/hypn4">@hypn4</a></td>
<td><a href="https://github.com/gmoz22">@gmoz22</a></td>
</tr>
<tr>
<td><a href="https://github.com/contributor">@contributor</a></td>
<td><a href="https://github.com/apaz-cli">@apaz-cli</a></td>
<td><a href="https://github.com/preynal">@preynal</a></td>
<td><a href="https://github.com/nims11">@nims11</a></td>
</tr>
<tr>
<td><a href="https://github.com/lreeves">@lreeves</a></td>
<td><a href="https://github.com/ktakayama">@ktakayama</a></td>
<td><a href="https://github.com/sentienthouseplant">@sentienthouseplant</a></td>
<td><a href="https://github.com/gcp">@gcp</a></td>
</tr>
<tr>
<td><a href="https://github.com/thehunmonkgroup">@thehunmonkgroup</a></td>
<td><a href="https://github.com/ctoth">@ctoth</a></td>
<td><a href="https://github.com/misteral">@misteral</a></td>
<td><a href="https://github.com/burnettk">@burnettk</a></td>
</tr>
<tr>
<td><a href="https://github.com/cryptekbits">@cryptekbits</a></td>
<td><a href="https://github.com/deansher">@deansher</a></td>
<td><a href="https://github.com/kennyfrc">@kennyfrc</a></td>
<td><a href="https://github.com/lentil32">@lentil32</a></td>
</tr>
<tr>
<td><a href="https://github.com/malkoG">@malkoG</a></td>
<td><a href="https://github.com/mubashir1osmani">@mubashir1osmani</a></td>
<td><a href="https://github.com/TimPut">@TimPut</a></td>
<td><a href="https://github.com/zjy1412">@zjy1412</a></td>
</tr>
<tr>
<td><a href="https://github.com/savioursho">@savioursho</a></td>
<td><a href="https://github.com/jayeshthk">@jayeshthk</a></td>
<td><a href="https://github.com/susliko">@susliko</a></td>
<td><a href="https://github.com/FeepingCreature">@FeepingCreature</a></td>
</tr>
<tr>
<td><a href="https://github.com/aelaguiz">@aelaguiz</a></td>
<td><a href="https://github.com/eltociear">@eltociear</a></td>
<td><a href="https://github.com/tao12345666333">@tao12345666333</a></td>
<td><a href="https://github.com/jpshack-at-palomar">@jpshack-at-palomar</a></td>
</tr>
<tr>
<td><a href="https://github.com/mbokinala">@mbokinala</a></td>
<td><a href="https://github.com/yamitzky">@yamitzky</a></td>
<td><a href="https://github.com/mobyvb">@mobyvb</a></td>
<td><a href="https://github.com/nicolasperez19">@nicolasperez19</a></td>
</tr>
<tr>
<td><a href="https://github.com/ozapinq">@ozapinq</a></td>
<td><a href="https://github.com/ryanfreckleton">@ryanfreckleton</a></td>
<td><a href="https://github.com/nhs000">@nhs000</a></td>
<td><a href="https://github.com/smh">@smh</a></td>
</tr>
<tr>
<td><a href="https://github.com/zhyu">@zhyu</a></td>
<td><a href="https://github.com/Skountz">@Skountz</a></td>
<td><a href="https://github.com/sestrella">@sestrella</a></td>
<td><a href="https://github.com/Netzvamp">@Netzvamp</a></td>
</tr>
<tr>
<td><a href="https://github.com/peterhadlaw">@peterhadlaw</a></td>
<td><a href="https://github.com/pauldw">@pauldw</a></td>
<td><a href="https://github.com/paulmaunders">@paulmaunders</a></td>
<td><a href="https://github.com/StevenTCramer">@StevenTCramer</a></td>
</tr>
<tr>
<td><a href="https://github.com/strayer">@strayer</a></td>
<td><a href="https://github.com/taha-yassine">@taha-yassine</a></td>
<td><a href="https://github.com/tamirzb">@tamirzb</a></td>
<td><a href="https://github.com/tgbender">@tgbender</a></td>
</tr>
<tr>
<td><a href="https://github.com/pcgeek86">@pcgeek86</a></td>
<td><a href="https://github.com/omri123">@omri123</a></td>
<td><a href="https://github.com/MatthewZMD">@MatthewZMD</a></td>
<td><a href="https://github.com/mbailey">@mbailey</a></td>
</tr>
<tr>
<td><a href="https://github.com/golergka">@golergka</a></td>
<td><a href="https://github.com/matfat55">@matfat55</a></td>
<td><a href="https://github.com/mtofano">@mtofano</a></td>
<td><a href="https://github.com/maledorak">@maledorak</a></td>
</tr>
<tr>
<td><a href="https://github.com/mlang">@mlang</a></td>
<td><a href="https://github.com/marcomayer">@marcomayer</a></td>
<td><a href="https://github.com/holoskii">@holoskii</a></td>
<td><a href="https://github.com/ffluk3">@ffluk3</a></td>
</tr>
<tr>
<td><a href="https://github.com/lattwood">@lattwood</a></td>
<td><a href="https://github.com/henderkes">@henderkes</a></td>
<td><a href="https://github.com/you-n-g">@you-n-g</a></td>
<td><a href="https://github.com/rti">@rti</a></td>
</tr>
<tr>
<td><a href="https://github.com/prmbiy">@prmbiy</a></td>
<td><a href="https://github.com/omarcinkonis">@omarcinkonis</a></td>
<td><a href="https://github.com/Oct4Pie">@Oct4Pie</a></td>
<td><a href="https://github.com/mark-asymbl">@mark-asymbl</a></td>
</tr>
<tr>
<td><a href="https://github.com/mdklab">@mdklab</a></td>
<td><a href="https://github.com/mario7421">@mario7421</a></td>
<td><a href="https://github.com/kAIto47802">@kAIto47802</a></td>
<td><a href="https://github.com/jvmncs">@jvmncs</a></td>
</tr>
<tr>
<td><a href="https://github.com/hydai">@hydai</a></td>
<td><a href="https://github.com/hstoklosa">@hstoklosa</a></td>
<td><a href="https://github.com/gordonlukch">@gordonlukch</a></td>
<td><a href="https://github.com/develmusa">@develmusa</a></td>
</tr>
<tr>
<td><a href="https://github.com/coredevorg">@coredevorg</a></td>
<td><a href="https://github.com/cantalupo555">@cantalupo555</a></td>
<td><a href="https://github.com/caetanominuzzo">@caetanominuzzo</a></td>
<td><a href="https://github.com/yzx9">@yzx9</a></td>
</tr>
<tr>
<td><a href="https://github.com/zackees">@zackees</a></td>
<td><a href="https://github.com/wietsevenema">@wietsevenema</a></td>
<td><a href="https://github.com/krewenki">@krewenki</a></td>
<td><a href="https://github.com/vinnymac">@vinnymac</a></td>
</tr>
<tr>
<td><a href="https://github.com/szepeviktor">@szepeviktor</a></td>
<td><a href="https://github.com/varchasgopalaswamy">@varchasgopalaswamy</a></td>
<td><a href="https://github.com/tanavamsikrishna">@tanavamsikrishna</a></td>
<td><a href="https://github.com/tylersatre">@tylersatre</a></td>
</tr>
<tr>
<td><a href="https://github.com/daysm">@daysm</a></td>
<td><a href="https://github.com/devriesd">@devriesd</a></td>
<td><a href="https://github.com/daniel-sc">@daniel-sc</a></td>
<td><a href="https://github.com/damms005">@damms005</a></td>
</tr>
<tr>
<td><a href="https://github.com/curran">@curran</a></td>
<td><a href="https://github.com/cclauss">@cclauss</a></td>
<td><a href="https://github.com/cjoach">@cjoach</a></td>
<td><a href="https://github.com/csala">@csala</a></td>
</tr>
<tr>
<td><a href="https://github.com/bexelbie">@bexelbie</a></td>
<td><a href="https://github.com/branchv">@branchv</a></td>
<td><a href="https://github.com/bkowalik">@bkowalik</a></td>
<td><a href="https://github.com/h0x91b">@h0x91b</a></td>
</tr>
<tr>
<td><a href="https://github.com/aroffe99">@aroffe99</a></td>
<td><a href="https://github.com/banjo">@banjo</a></td>
<td><a href="https://github.com/anjor">@anjor</a></td>
<td><a href="https://github.com/andreypopp">@andreypopp</a></td>
</tr>
<tr>
<td><a href="https://github.com/ivnvxd">@ivnvxd</a></td>
<td><a href="https://github.com/andreakeesys">@andreakeesys</a></td>
<td><a href="https://github.com/ameramayreh">@ameramayreh</a></td>
<td><a href="https://github.com/a1ooha">@a1ooha</a></td>
</tr>
<tr>
<td><a href="https://github.com/maliayas">@maliayas</a></td>
<td><a href="https://github.com/akirak">@akirak</a></td>
<td><a href="https://github.com/adrianlzt">@adrianlzt</a></td>
<td><a href="https://github.com/codefromthecrypt">@codefromthecrypt</a></td>
</tr>
<tr>
<td><a href="https://github.com/aweis89">@aweis89</a></td>
<td><a href="https://github.com/aj47">@aj47</a></td>
<td><a href="https://github.com/noitcudni">@noitcudni</a></td>
<td><a href="https://github.com/solatis">@solatis</a></td>
</tr>
<tr>
<td><a href="https://github.com/webkonstantin">@webkonstantin</a></td>
<td><a href="https://github.com/khulnasoft-bot">@khulnasoft-bot</a></td>
<td><a href="https://github.com/KebobZ">@KebobZ</a></td>
<td><a href="https://github.com/acro5piano">@acro5piano</a></td>
</tr>
<tr>
<td><a href="https://github.com/josx">@josx</a></td>
<td><a href="https://github.com/joshvera">@joshvera</a></td>
<td><a href="https://github.com/jklina">@jklina</a></td>
<td><a href="https://github.com/jkeys089">@jkeys089</a></td>
</tr>
<tr>
<td><a href="https://github.com/johanvts">@johanvts</a></td>
<td><a href="https://github.com/gengjiawen">@gengjiawen</a></td>
<td><a href="https://github.com/jevon">@jevon</a></td>
<td><a href="https://github.com/jesstelford">@jesstelford</a></td>
</tr>
<tr>
<td><a href="https://github.com/JeongJuhyeon">@JeongJuhyeon</a></td>
<td><a href="https://github.com/jackhallam">@jackhallam</a></td>
<td><a href="https://github.com/Mushoz">@Mushoz</a></td>
<td><a href="https://github.com/zestysoft">@zestysoft</a></td>
</tr>
<tr>
<td><a href="https://github.com/gwpl">@gwpl</a></td>
<td><a href="https://github.com/garrett-hopper">@garrett-hopper</a></td>
<td><a href="https://github.com/filiptrplan">@filiptrplan</a></td>
<td><a href="https://github.com/FelixLisczyk">@FelixLisczyk</a></td>
</tr>
<tr>
<td><a href="https://github.com/evnoj">@evnoj</a></td>
<td><a href="https://github.com/erykwieliczko">@erykwieliczko</a></td>
<td><a href="https://github.com/elohmeier">@elohmeier</a></td>
<td><a href="https://github.com/emmanuel-ferdman">@emmanuel-ferdman</a></td>
</tr>
<tr>
<td><a href="https://github.com/spdustin">@spdustin</a></td>
<td></td>
<td></td>
<td></td>
</tr>
</tbody>
</table>