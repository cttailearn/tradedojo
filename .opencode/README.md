# .opencode/ — 项目级 opencode 配置

本目录存放 TradeDojo 项目级别的 opencode 配置。opencode 会从**当前工作目录向上查找**到仓库根,合并这里的项目配置与用户全局配置(项目覆盖全局)。

## 文件说明

| 文件/目录 | 作用 |
|-----------|------|
| `../opencode.json` | 项目配置(指令、模型、权限等),声明 `$schema` 便于校验 |
| `../AGENTS.md` | 项目指南,opencode 每次会话自动加载为上下文 |
| `command/*.md` | 项目级斜杠命令(如 `/check`) |
| `agent/*.md` | 项目级 agent(目前未定义) |
| `skill/*/SKILL.md` | 项目级 skill(目前未定义) |

## 常用操作

- **添加命令**:在 `command/` 下新建 `<name>.md`,frontmatter 写 `description`,`$ARGUMENTS` 表示用户输入。
- **添加 agent**:在 `agent/` 下新建 `<name>.md`,frontmatter 写 `description`/`mode`/`model`,正文即 prompt。
- **添加 skill**:在 `skill/<name>/` 下创建 `SKILL.md`,`name` 必须与目录名一致。
- 修改任何配置后**需重启 opencode** 才生效(配置只在启动时加载一次)。

## 注意

- `.omo/`(OhMyOpenCode 计划)、`.codegraph/`(索引)、`.trae/`(Trae IDE)为本地状态目录,已在 `.gitignore` 中排除,勿提交。
- 项目配置保持精简:可复用的 agent/skill/命令优先放用户全局目录(`~/.config/opencode/`)。
