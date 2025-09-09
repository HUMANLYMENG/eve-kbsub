# eve-kbsub
killmail subscription program for Eve online

# EVE Online 击杀报告生成器

一个实时监控 EVE Online 击杀事件并自动生成分享图片的 Python 脚本。

## 安装与配置

1. **准备文件**
    - **字体**: 在项目根目录创建 `fonts` 文件夹，并放入所需字体。
    - **EVE SDE**: 下载 EVE 静态数据，并将 `sde` 文件夹放入项目根目录。

2.  **修改配置 (最重要)**
    - **编辑 `include.py` 文件**，填入你自己的 `QUEUE_ID`, `USER_AGENT` 和 `vips` 列表。

## 运行

```bash
python cloud_subkill.py
```
生成的图片会保存在 `tmp` 文件夹中。

## 许可证

[MIT](LICENSE)
