# sprite-contract-check

**像素真的变了，还是图集重新排列了？**

离线比较两份 Aseprite PNG + JSON 导出的 Python 命令行工具。按明确的帧名匹配，
根据裁剪信息还原原始画布，区分排列变化、像素变化、时长、标签及帧的增删。
不需要安装 Aseprite，不上传图片，也不需要 API 密钥。

[English](README.md) · [完整比较规则与限制](docs/contract.md)


## 安装与演示

需要 Python 3.10+ 和 Pillow 12.2–12.x。从本仓库安装（目前不声称已发布到 PyPI）：

```sh
python -m pip install .
sprite-contract-check examples/demo/before.json examples/demo/before.png examples/demo/repacked.json examples/demo/repacked.png --old-indices examples/demo/before-indices.json --new-indices examples/demo/repacked-indices.json --json result.json --html result.html
```

本地打开 result.html。八个原创演示精灵的排列、图集尺寸和 JSON 结构发生变化，
但还原后的像素不变，因此退出码为 0。把命令里的三处 repacked 改为 changed，
即可查看删除一帧、修改一个像素、改变一帧时长和一个标签的报告，退出码为 1。

## CI 使用

- 退出码 0：符合选定的比较规则
- 退出码 1：输入有效，但合同有变化，需要审核
- 退出码 2：输入无效、不支持的导出形式或写报告失败

标准输出始终为 JSON（命令参数错误除外）。--json 另存文件；--html 生成完全离线、
无脚本、内嵌预览图的 HTML。结果不包含路径和时间戳，便于稳定比较。
默认 content 模式允许重新排列及等价裁剪；依赖固定图集位置的引擎可使用
--mode coordinates，连排列或图集尺寸变化也会导致失败。

## 明确的名称和索引

支持 Aseprite JSON 数组与哈希格式。不会根据名称、数组顺序或像素相似度猜测匹配。
--mapping rename.json 可以提供旧名到新名的一对一映射，但改名仍是合同变化。

标签引用的是源动画帧索引。排除空帧后，导出顺序不一定能代表它。
有标签时必须通过 --old-indices 和 --new-indices 提供完整的名称到源索引 JSON，
例如 {"idle/0": 0, "idle/1": 1}；也可在每帧明确提供整数 index。
索引必须来自已知的导出约定，不能猜。重复索引、标签跨越缺失索引均拒绝处理。

## 范围与限制

精确比较 RGBA、原始画布大小、时长、名称、源索引及标签；只有 alpha 为零的隐藏
RGB 被归零。仅忽略 meta.app、meta.version、meta.image 三个来源信息字段。
PNG 路径需明确传入；绝不把帧名或 meta.image 当路径读取。
未知字段保守比较。旋转、缩放、非空 layers/slices、APNG 及错误边界均不支持。
支持最高 8 位采样及调色板 PNG；16 位 PNG 会被拒绝，避免转换导致像素差异丢失。

JSON 每份最多 4 MiB，PNG 每份最多 32 MiB；最多 2048 帧；HTML 最多展示 128 帧，
JSON 保留完整结果。其他资源限制和元数据规范化规则请见完整规则文档。
可信基线必须人工审核：两份同样错误的导出仍可比较通过，本工具不能证明导出
符合原始源文件。它不修改 Aseprite，不负责打包，也不是通用图像编辑器。

## 需求依据与开发

[Aseprite #5626](https://github.com/aseprite/aseprite/issues/5626) 的排列变化、
[#6059](https://github.com/aseprite/aseprite/issues/6059) 的索引歧义、
[#5340](https://github.com/aseprite/aseprite/issues/5340) 的平台元数据差异、
[#5663](https://github.com/aseprite/aseprite/issues/5663) 的图集与数据不一致、
[#6040](https://github.com/aseprite/aseprite/issues/6040) 的 JSON 缺失问题，
说明导出约定校验有实际价值。这是独立项目，不代表 Aseprite 官方支持或修复。

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python examples/generate_demo.py
```

提供 Linux、Windows、macOS 的 GitHub Actions 模板；本地测试通过不代表远程 CI 已运行。
代码和原创演示素材均采用 MIT 许可。
