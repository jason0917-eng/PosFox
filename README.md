# PosFox

从论文 PDF 生成海报，再重建为可编辑的 HTML / SVG，导出 PNG / PDF。

这套 workflow 在当前 agent Harness 中执行：模型负责阅读、讨论、图生成和视觉判断，本地 Python 负责素材提取、文件构建、渲染与校验。需要 Harness 提供图生成能力；单独执行 Python 不会自动生成海报。

## 流程

1. 解析完整论文，提取保留图例、坐标轴和出处的图表素材。
2. 内容、科学核查、视觉规划三个角色并行阅读同一份材料；必要时围绕争议做一次简短回调，由主执行者落实修改。
3. 优先采用用户给出的主参考，生成包含完整正文和图表的海报图。生成阶段参考 [PosFox-Gen](https://github.com/LawrenceRiver/PosFox-Gen-skill)。
4. 按生成图重建可编辑 HTML / SVG，使用论文原图和准确数值替换生成近似；重建与局部修复参考 [FigFox](https://github.com/LawrenceRiver/FigFox)。
5. 做一次按语义区域划分的视觉对照。有明确问题时执行一批局部修复，验证受影响对象与导出文件；没有问题则直接交付。
6. 保留来源、实际审阅记录、阶段耗时和校验结果，交付 HTML、SVG、PNG、PDF。

图生成通常一次，必要时最多重生成一次；未解决的实质错误会阻塞交付。文字、线条和原生表格可编辑；保留为论文原图的图像对象可移动、替换，其内部标签不会自动变成独立文字。

## 安装与使用

```sh
git clone https://github.com/jason0917-eng/PosFox.git
cd PosFox
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

将 `skills/posfoxgen` 注册到 Harness 的 skills 目录。例如在 Codex 中，从仓库根目录执行：

```sh
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/posfoxgen" ~/.codex/skills/posfoxgen
```

如果同名 Skill 已存在，先检查其位置。随后在新会话中调用 `$posfoxgen`，提供论文 PDF 和可选的设计参考。模型阶段使用 Harness 当前能力，无需额外搭建模型 API 服务或配置本项目专用 API key。

Skill 入口：[SKILL.md](skills/posfoxgen/SKILL.md)。阶段命令与文件契约：[workflow.md](skills/posfoxgen/references/workflow.md)。

```sh
python skills/posfoxgen/scripts/run.py --help
python skills/posfoxgen/scripts/run.py init --run runs/example --paper /absolute/paper.pdf --split development
python skills/posfoxgen/scripts/run.py assets /absolute/paper.pdf --out runs/example/source
python skills/posfoxgen/scripts/run.py status --run runs/example
python skills/posfoxgen/scripts/run.py validate-delivery --run runs/example
```

`assets`、`editable` 和 `render` 是本地文件工具，不会代替模型完成科学判断。阶段收据记录实际输入与输出，最终校验会重新检查文件、来源绑定、渲染报告与审阅记录。

## 渲染与可选修复引擎

渲染需要本机 Chrome / Chromium。未自动找到时，用 `POSFOXGEN_CHROMIUM` 指定可执行文件。字体也需要本地安装；工具会检查实际字体与文字溢出。

使用 FigFox 原生局部编辑桥接器或运行其集成测试前，下载固定版本源码：

```sh
git clone https://github.com/LawrenceRiver/FigFox.git vendor/figfox
git -C vendor/figfox checkout 21ffc01271904d6c5610f0f96afd84530968f11e
```

桥接器仅加载确定性的原生编辑合同，不调用上游模型 API。其余研究来源的版本见 [vendor/sources.json](vendor/sources.json)。

## 参考与检查

生成前的逻辑与证据核查、原图保留、可编辑重建和局部修复是本流程的主要约束。海报规划与质量诊断也参考了 [AutoDesign](https://github.com/Yaxin9Luo/AutoDesign)、[Paper2Poster](https://github.com/Paper2Poster/Paper2Poster) 和 [FigFox Gen](https://github.com/LawrenceRiver/FigFox-Gen-skill)。来源和适用边界见 [质量研究记录](references/poster-quality-research.md)。

仓库只附轻量参考清单，作者海报原件按视觉参考用途单独下载：

```sh
python scripts/reference_library.py
python scripts/reference_library.py --verify-only
```

原作者海报的内容和许可归各自作者；清单不授予图片再分发权。本地七维质量判断与官方 PosterBench 执行分开记录，单个演示不作为稳定速度或泛化效果的证据。

开发检查：

```sh
python -m pip install pytest
python -m pytest -q
```

完整测试需要上述浏览器、常用字体及固定 FigFox 源码。用户论文、海报原件、缓存、运行记录和个人开发笔记不随源码发布。
