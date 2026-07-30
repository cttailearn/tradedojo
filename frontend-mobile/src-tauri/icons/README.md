# 占位说明

Tauri 在构建时需要图标(参见 `tauri.conf.json → bundle.icon`)。
首次正式打包时,请用以下脚本替换为正式图标:

```bash
# 在 frontend-mobile/ 目录下
# 用任意 1024x1024 PNG 通过 tauri 官方命令生成全套
npx @tauri-apps/cli@^2 icon ./src-tauri/icons/source.png
```

若暂时没有设计稿,可先运行:
```bash
npx @tauri-apps/cli@^2 icon ./src-tauri/icons/icon.png
```
你只要丢一个 `icon.png` 到该目录,命令会自动生成 32x32、128x128、128x128@2x、icon.ico、icon.icns。
