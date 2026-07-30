/**
 * Tradedojo Mobile - Tauri 2.0 库入口
 *
 * 注册的 plugin 全是官方列表内:
 * - dialog:  原生确认对话框(注册/退出等)
 * - fs:      本地持久化 token/钱包(替代 localStorage,可选)
 * - http:    若需绕开 CORS 可走 https://api.cttai.art
 * - os:      平台判断 + locale
 * - shell:   打开外部链接
 * - store:   替代 localStorage 的 KV 持久化
 * - log:     把 panic / 业务 warn 写入 Android logcat
 * - notification: 训练结果通知(可选,一般不弹)
 *
 * 暴露命令(供前端 invoke):
 * - get_api_base  → 给前端读取当前生效的 API 地址
 * - get_platform  → "android" / "ios" / 等
 */
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![get_api_base, get_platform])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[tauri::command]
fn get_api_base() -> String {
    // 优先从环境变量读(打包时通过 tauri.conf.json 的 .env 注入)
    std::env::var("TRADEDOJO_API_BASE").unwrap_or_else(|_| {
        "https://api.cttai.art/api".to_string()
    })
}

#[tauri::command]
fn get_platform() -> String {
    #[cfg(target_os = "android")]
    return "android".to_string();
    #[cfg(target_os = "ios")]
    return "ios".to_string();
    #[cfg(target_os = "windows")]
    return "windows".to_string();
    #[cfg(target_os = "macos")]
    return "macos".to_string();
    #[cfg(target_os = "linux")]
    return "linux".to_string();
}
