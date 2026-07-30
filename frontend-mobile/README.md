# 操盘道场 - Mobile (Tauri 2.0 APK)

Vue 3 + Vite 5 + Vant 4 + Tauri 2.0,移动端训练 App。
**仅包含训练端(/train/* 路由)**,与 `frontend/` 主后台前端解耦。

> ✅ **已构建过 release APK 并用 PKCS12 upload-keystore 签名**。产物: `dist/操盘道场-v1.0.0.apk` (universal 72.3 MB)。可直接 `adb install -r`,或上传 Play Store。

## 技术栈

| 层 | 选型 | 用途 |
|---|---|---|
| 框架 | Vue 3 (Composition API + `<script setup>`) | UI |
| 构建 | Vite 5 | dev + build |
| 路由 | Vue Router 4(hash 模式) | SPA,兼容 tauri:// / file:// |
| 状态 | Pinia 2 | 训练端 token / wallet |
| UI | Vant 4 | 移动组件(Stepper/Tabs/Collapse/Switch...) |
| 图表 | ECharts 5 | K线蜡烛 + 资金曲线 |
| 适配 | postcss-mobile-forever | 自动 px → rem,设计稿基准 375 |
| HTTP | Axios | Bearer + CSRF + 401 跳转 |
| 容器 | **Tauri 2.0** | 原生 Android APK 打包 |

## 目录结构

```
frontend-mobile/
├── package.json                # 依赖
├── vite.config.js              # dev proxy + build (manualChunks)
├── postcss.config.js           # 1rem=100px @ 375 视口
├── index.html                  # SPA 入口 (含 viewport-fit=cover)
├── .env.development            # dev: /api 走 Vite 代理
├── .env.production             # prod: https://api.cttai.art/api
└── src/
    ├── main.js                 # Vue 入口 + isTauri() 检测
    ├── App.vue                 # 路由过渡
    ├── router/index.js         # 训练端路由
    ├── stores/trainAuth.js     # token + wallet
    ├── api/
    │   ├── index.js            # axios 实例
    │   └── modules.js          # trainApi 等
    ├── utils/trainFee.js       # 训练费公式(与后端严格一致)
    ├── layouts/AppShell.vue    # 底部 TabBar + NavBar + 内容区
    ├── components/
    │   ├── NavBar.vue          # 顶部导航
    │   └── BottomTabBar.vue    # 5 个 Tab:首页/新训练/统计/钱包/我的
    ├── views/
    │   ├── Login.vue           # 登录/注册
    │   ├── Home.vue            # 训练记录 + 余额 + 新训练 CTA
    │   ├── Setup.vue           # 发起训练参数(分卡片,适合长表单)
    │   ├── Trade.vue           # 交易训练(K线 + 资金曲线 + 下单/持仓/成交)
    │   ├── Report.vue          # 训练诊断报告
    │   ├── Stats.vue           # 交割单统计(KPI + 分布图)
    │   ├── Wallet.vue          # 兑换码充值
    │   └── Me.vue              # 个人中心 + 深色模式 + 退出
    └── styles/
        ├── variables.css       # 设计 token
        └── main.css            # 全局 + 安全区 + Vant 主题

src-tauri/
├── tauri.conf.json             # bundle / android / CSP / abiTargets
├── Cargo.toml                  # tauri 2 + dialog/haptics/os/status-bar
├── build.rs
├── src/
│   ├── main.rs
│   └── lib.rs                  # get_api_base / get_platform commands
├── capabilities/
│   ├── default.json            # 跨平台权限
│   └── android.json            # Android 专属 (含 biometric)
└── icons/                      # 见 icons/README.md
```

## 启动方式

### ① 仅 Web Dev(纯浏览器开发,不打包 APK)

```powershell
cd frontend-mobile
npm install
npm run dev          # http://localhost:5174 (手机扫码也行,wifi 内 0.0.0.0)
```

Web dev 模式默认 `VITE_API_BASE=/api`(走 Vite 代理 → 127.0.0.1:8000)。
如果想直接打线上:
```powershell
New-Item .env.development.local -ItemType File -Value "VITE_API_BASE=https://api.cttai.art/api"
```

### ② 打包 Android APK

> 假设你已经装好:Node 20+、Rust(clang)、Android Studio(Hedgehog 2023+)、Android SDK 34、NDK 26+、JDK 17。
>
> `cargo tauri android` 第一次会帮你装好 Android Gradle 插件。

**⚠️ 中国网络注意:`services.gradle.org` 与 `dl.google.com` 经常超时,务必设好国内镜像,否则 Gradle wrapper 下载会卡死。**

```powershell
# 一次性国内镜像配置(用户级,写入 ~/.gradle/init.gradle):
# 见下方 "国内 Gradle 镜像配置" 一节

# 一次性安装
cd frontend-mobile
npm install
rustup target add aarch64-linux-android armv7-linux-androideabi x86_64-linux-android

# 生成 Tauri 容器工程(只需第一次)
npx @tauri-apps/cli@^2 android init

# 构建 APK
npx @tauri-apps/cli@^2 android build --apk
# 产物:src-tauri/gen/android/app/build/outputs/apk/universal/release/app-universal-release-unsigned.apk

# 签名(便于真机调试;生产请用 Play 签名 key)
powershell -ExecutionPolicy Bypass -File scripts/sign-debug-apk.ps1 `
    -ApkPath src-tauri/gen/android/app/build/outputs/apk/universal/release/app-universal-release-unsigned.apk
# 签名后,apk 可以直接 adb install
```

### ②.b 国内 Gradle 镜像配置(必须,否则卡下载)

`%USERPROFILE%\.gradle\init.gradle`(本项目已写好):
```groovy
allprojects {
    repositories {
        maven { url 'https://maven.aliyun.com/repository/public' }
        maven { url 'https://maven.aliyun.com/repository/google' }
        maven { url 'https://maven.aliyun.com/repository/gradle-plugin' }
    }
}
settingsEvaluated { s ->
    s.pluginManagement {
        repositories {
            maven { url 'https://maven.aliyun.com/repository/public' }
            maven { url 'https://maven.aliyun.com/repository/gradle-plugin' }
        }
    }
}
```

修改 `src-tauri/gen/android/gradle/wrapper/gradle-wrapper.properties`:
```
distributionUrl=https\://mirrors.cloud.tencent.com/gradle/gradle-8.14.3-bin.zip
```

### ③ 离线 / 局域网测试

1. 让手机和电脑在同一 wifi
2. 电脑跑 `npm run dev` (`--host 0.0.0.0`)
3. 手机浏览器访问 `http://你电脑IP:5174`
4. Chrome DevTools 手机模拟器也能直接看效果

## 路由结构

| 路径 | 组件 | 说明 |
|---|---|---|
| `/` | Login | 登录/注册(公开) |
| `/home` | Home | 训练列表 + 余额 |
| `/setup` | Setup | 发起训练参数 |
| `/stats` | Stats | 交割单统计 |
| `/wallet` | Wallet | 兑换码充值 |
| `/me` | Me | 个人中心 |
| `/trade/:id` | Trade | K线交易(全屏,无 TabBar) |
| `/report/:id` | Report | 诊断报告(全屏) |

## 移动端适配要点

1. **rem 适配**:`postcss-mobile-forever` 把所有 px → rem,基准 375 视口,1rem=100px。
2. **安全区**:`padding-top: env(safe-area-inset-top)` 用在 AppShell / NavBar / 弹窗。
3. **底部 TabBar**:固定底部 + `padding-bottom: env(safe-area-inset-bottom)`。
4. **H5 软键盘**:`<input>` 默认会触发 Android 软键盘,带 `viewport-fit=cover` 配合 `100dvh` 兜底。
5. **图表**:`echarts` 在窄屏上需要 `showSymbol:false` + `dataZoom` 隐藏,本项目已优化。
6. **横竖屏**:Tauri 默认锁竖屏(可在 `tauri.conf.json` android 段加 `"orientation": "portrait"`;默认通常就是 `portrait`,可在 AndroidManifest.xml 修改)。

## 与后端的集成

- **Web dev**:Vite proxy → `http://127.0.0.1:8000`
- **APK 内**:`VITE_API_BASE=https://api.cttai.art/api`(在 `.env.production`)
- 鉴权:token 存 `localStorage`,axios 拦截器自动 `Authorization: Bearer <token>`
- CSRF:写操作自动带 `X-CSRF-Token` cookie
- 401:Vant `showToast` + 跳 `/`

## 后端需确认

后端需做两件事(否则 APK 内登录会失败):

1. **CORS** 允许 Tauri 自定义协议来源。建议在 `backend/app/main.py` middleware 里加:
   ```python
   allow_origins=[..., "tauri://localhost", "https://tauri.localhost", "asset://localhost", "https://asset.localhost"]
   ```
2. **Cookie SameSite**:`withCredentials=true` 在跨站时需要 `SameSite=None; Secure`。若 APK 是 https 加载域名,这没问题;若用 http 加载(`tauri://localhost` 是 http),则要改成 IP 直连或确保后端证书 + `Secure` 都能用。

## Android 代码签名(已配置)

按照官方 [Tauri 2 Android Sign](https://v2.tauri.org.cn/distribute/sign/android/) 配置完成。

**1. 创建 keystore(已在 %USERPROFILE%\upload-keystore.jks,迁移到 PKCS12 格式)**

```powershell
keytool -genkey -v -keystore $env:USERPROFILE\upload-keystore.jks `
    -storetype JKS -keyalg RSA -keysize 2048 -validity 10000 `
    -alias upload `
    -storepass tradedojo2026 -keypass tradedojo2026 `
    -dname "CN=cttai, OU=tradedojo, O=cttai, L=Beijing, S=Beijing, C=CN"

# keytool 提示迁移到 PKCS12,跟着做:
keytool -importkeystore -srckeystore $env:USERPROFILE\upload-keystore.jks `
    -destkeystore $env:USERPROFILE\upload-keystore.jks `
    -deststoretype pkcs12 -storepass tradedojo2026 -noprompt
```

⚠️ **永远不要把 keystore / keystore.properties 提交到 git**。当前 `.gitignore` 已排除:
```
*.jks
*.keystore
keystore.properties
```

**2. 配置 `src-tauri/gen/android/keystore.properties`(已存在)**

```
password=tradedojo2026
keyAlias=upload
storeFile=C:\\Users\\cttai\\upload-keystore.jks
```

**3. `app/build.gradle.kts` 加 signingConfig(已修改)**

照官方文档在 `android { ... }` 加:
```kotlin
import java.io.FileInputStream  // 顶部

signingConfigs {
    create("release") {
        val keystorePropertiesFile = rootProject.file("keystore.properties")
        val keystoreProperties = Properties()
        if (keystorePropertiesFile.exists()) {
            keystoreProperties.load(FileInputStream(keystorePropertiesFile))
        }
        keyAlias    = keystoreProperties["keyAlias"]   as String
        keyPassword = keystoreProperties["password"]   as String
        storeFile   = file(keystoreProperties["storeFile"] as String)
        storePassword = keystoreProperties["password"] as String
    }
}
buildTypes {
    getByName("release") {
        signingConfig = signingConfigs.getByName("release")
        // ...
    }
}
```

**4. 注意 "操盘道场" 应用名**

Tauri `productName` 在桌面/开发期生效,但 **Android APK 的 `application-label` 来自 `gen/android/app/src/main/res/values/strings.xml`**。改了 `productName` 之后必须同步改 `strings.xml`:

```xml
<resources>
    <string name="app_name">"操盘道场"</string>
    <string name="main_activity_title">"操盘道场"</string>
</resources>
```

> 如果跑过 `tauri android init` 重生成,这个文件会被模板覆盖。后续如果改了 productName,记得手动同步 strings.xml,或者写一个 post-init 脚本。

**5. 验证签名**

```powershell
$apksigner = "$env:ANDROID_HOME\build-tools\35.0.0\apksigner.bat"
& $apksigner verify --print-certs "dist\操盘道场-v1.0.0.apk"
```

应输出:
```
Signer #1 certificate DN: CN=cttai, OU=tradedojo, O=cttai, L=Beijing, ST=Beijing, C=CN
Signer #1 certificate SHA-256 digest: c272363c827d8f56728dcdbe89985861e8ad9b1ba653ec827c898ad73ab5b0be
Verified using v2 scheme (APK Signature Scheme v2): true
```

## 常用命令

```bash
npm run dev                # Web dev (http://localhost:5174)
npm run build              # Web 生产构建 → dist/
npm run build:tauri        # 等价于:tauri build (桌面端)
npx tauri android dev      # Android 真机/模拟器开发
npx tauri android build    # Android APK/AAB 构建
```

## 已知约束

- Tauri **不支持 npm 内置的 `tauri android` 命令**,需要在容器工程根目录运行。
- 首次构建安卓 APK 会下载约 500MB 的 Gradle 依赖,后续增量构建秒级。
- iOS 暂未配置(`tauri ios`),如需请补 `tauri-plugin-*` 在 `Cargo.toml` 加 iOS 段。
- 字体使用系统默认 `PingFang SC` / `Microsoft YaHei`,未内置字体包(如需可加 `unfonts`)。

## 产物路径

| 类型 | 路径 |
|---|---|
| Web dist | `dist/` |
| **已签名 APK(可直接装机)** | **`dist/操盘道场-v1.0.0.apk`** (universal, 72.3 MB, APK v2 签名) |
| APK 原始输出 | `src-tauri/gen/android/app/build/outputs/apk/universal/release/app-universal-release.apk` |
| AAB(Play)   | `src-tauri/gen/android/app/build/outputs/bundle/release/app-release.aab` |

打包示例:
```powershell
# 装机测试(连真机 adb)
adb install -r 'dist\操盘道场-v1.0.0.apk'

# 卸载
adb uninstall art.cttai.tradedojo.mobile

# 验证 APK 签名(看证书)
& "$env:ANDROID_HOME\build-tools\35.0.0\apksigner.bat" verify --print-certs 'dist\操盘道场-v1.0.0.apk'

# 验证 APK 元数据(aapt2 自带,看 application-label 等)
& aapt2.exe dump badging 'dist\操盘道场-v1.0.0.apk'
```

签名信息(仅本机调试用,正式上架请用 Play Store 自己的签名 key):
- Keystore:`%USERPROFILE%\upload-keystore.jks`(PKCS12)
- Alias:`upload`
- Password:`tradedojo2026`
- DN:`CN=cttai, OU=tradedojo, O=cttai, L=Beijing, ST=Beijing, C=CN`
- SHA-256:`c272363c827d8f56728dcdbe89985861e8ad9b1ba653ec827c898ad73ab5b0be`
