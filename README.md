# 壁纸自动切换器

一个功能丰富的桌面壁纸自动切换应用。

## 功能特性

- 📁 **多壁纸来源文件夹**：支持添加多个文件夹作为壁纸来源
- ⏰ **定时切换**：支持每5分钟、30分钟、每小时、每天自动切换
- 🎲 **多种切换模式**：
  - 顺序：按文件名顺序切换
  - 随机：随机选择壁纸
  - 按修改时间：按文件修改时间新旧顺序
- 🖼️ **预览与手动控制**：实时预览当前壁纸，手动上一张/下一张/跳过/应用
- 🖥️ **多显示器支持**：可为每个显示器分别设置不同壁纸
- 💾 **壁纸缓存**：内置缓存机制避免重复加载大图
- 📜 **历史记录**：记录壁纸切换历史，可双击重新应用

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 项目结构

```
├── main.py                    # 入口文件
├── requirements.txt           # 依赖列表
├── config/
│   └── config_manager.py      # 配置管理
├── core/
│   ├── cache_manager.py       # 缓存与历史记录
│   ├── monitor_manager.py     # 显示器检测
│   ├── wallpaper_setter.py    # 壁纸设置（Windows API）
│   └── scheduler.py           # 调度器与切换逻辑
└── ui/
    ├── main_window.py         # 主窗口界面
    └── system_tray.py         # 系统托盘
```
