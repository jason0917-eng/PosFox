# 科研海报质量标准：原始依据与 POSFOXGEN 接法

2026-11-16 回查；本文件是研究结论和接入建议，不代表已经修改 workflow、运行官方评分或完成海报验收。详细字段、逐项来源、源码 SHA256 和本地位置见 [JSON](poster-quality-research.json)。

应当把“论文内容是否完整讲清楚”“一眼看起来是否舒服”“重建有没有损伤”分开检查，再按统一维度汇总。现有研究确实讨论了用户提出的内容密度、图表缩放和覆盖、字体、对齐、空白、拼贴及背景冲突。没有发现可跨学科、跨尺寸直接通用的固定字数或图表占比；背景融合也没有查到一套公认的独立分数。

## 1. 固定七维作为主评分，逻辑正确作为阻塞门

[AutoDesign 论文附录 A.4](https://arxiv.org/abs/2608.13560)与[官方固定 rubric](https://github.com/Yaxin9Luo/AutoDesign/blob/bd635851ef8a2ae257e2bf4c8cd4e984ea3fff1e/autodesign/evaluator/poster_rubric.py)一致，采用下列七维，各维 0–10，权重合计 100。

| 维度 | 权重 | 实际评什么 | 所有者 |
| --- | ---: | --- | --- |
| 忠实性 | 10 | 数字、实体、结论和视觉证据与论文一致 | 程序证据+视觉语义审稿 |
| 内容覆盖 | 10 | 问题、方法、证据、结论的研究主线 | 视觉语义审稿 |
| 信息密度与综合 | 15 | 内容占用、OCR框面积、空洞、正文截图 | 程序 |
| 视觉证据 | 10 | 图表相关、可读，附近有解释和结论 | 程序辅助+视觉语义审稿 |
| 布局完整性 | 20 | 画布/比例、裁切、重叠、越界、占位图 | 程序 |
| 阅读性 | 25 | 海报尺度可读性、层级、扫描路径、平衡、拥挤 | 程序+视觉语义审稿 |
| 专业审美 | 10 | 字体、克制的配色、整体构图一致性 | 视觉语义审稿 |

先计算 `Σ(权重 × 维度分/10)`，再取布局损伤、展示可用性、可见严重故障、渲染完整性各上限中的最严格值。普通 P0 上限 40，不是只减几分。固定协议通过线 70，但“得分到 70”不能代替本项目要求的逻辑无错；事实/逻辑 blocker 必须独立阻止进入 best image 和最终导出。混合维度在当前源码中对可用的程序与语义分取平均；缺少语义审稿时，不能把程序预检冒称完整官方评测。见[实际聚合源码](https://github.com/Yaxin9Luo/AutoDesign/blob/bd635851ef8a2ae257e2bf4c8cd4e984ea3fff1e/autodesign/evaluator/quality_rubric.py)。

必须区分三套东西：固定 PosterBench 七维；AutoDesign portable Skill 的七项 1–5 分、均分至少 3.75 且零 blocker 的生成审稿；旧 `vlm_benchmark.py` 提示中的另一组近似权重。它们不能混用。尤其不能读到旧提示里的密度 35，就声称固定基准密度权重是 35。

## 2. 用户关注的问题已经有哪些依据

[Paper2Poster 的官方布局评分提示](https://github.com/Paper2Poster/Paper2Poster/blob/70fc6f7b778bc8c9bfecc22875eff66f4eb65f93/utils/prompt_templates/aesthetic_layout_judge.yaml)直接检查对齐、间距、留白和阅读路径，并以 1–5 分明确区分可辨结构、接近专业、完全协调。其[图像评分](https://github.com/Paper2Poster/Paper2Poster/blob/70fc6f7b778bc8c9bfecc22875eff66f4eb65f93/utils/prompt_templates/aesthetic_element_judge.yaml)检查清晰度、标签/图例、配色和风格一致；[吸引力评分](https://github.com/Paper2Poster/Paper2Poster/blob/70fc6f7b778bc8c9bfecc22875eff66f4eb65f93/utils/prompt_templates/aesthetic_engagement_judge.yaml)检查字体、颜色、平衡和视觉流；[逻辑评分](https://github.com/Paper2Poster/Paper2Poster/blob/70fc6f7b778bc8c9bfecc22875eff66f4eb65f93/utils/prompt_templates/information_logic_judge.yaml)检查跨区块是否存在推理跳跃。这些都是可直接变成生成提示和逐块验收问题的锚点。

[Paper2Poster 论文](https://arxiv.org/html/2505.21497v2)还采用六维视觉语义评分和 PaperQuiz。后者检验读者能否只看海报回答论文问题，再以人类海报长度中位数 W 调整长度 L：`s_a = s_r × (1 + 1/max(1,L/W))`。短到 W 以下不再额外获益，因而不能靠删成几个 slogan 获胜。CLIP 视觉相似度和语言 PPL 各有局限，均不能独自证明科学准确或美学质量。

[PosterGen CVPR2026 最终论文](https://openaccess.thecvf.com/content/CVPR2026F/papers/Zhang_PosterGen_Aesthetic-Aware_Multi-Modal_Paper-to-Poster_Generation_Via_Multi-Agent_LLMs_CVPRF_2026_paper.pdf)将叙事、布局、颜色和字体变成前置规划。最终版 Table 2–4 区分 7 项内容（Layering/Coverage/Depth/Completeness/ABT/Flow/Conciseness）和 13 项审美：布局的 Grid/Whitespace/Anchor/Balance，颜色的 Palette/Hierarchy/Contrast/Source，字体的 Font/Emphasis/Legibility，以及 Alignment/Robustness，均为 1–5 分。它比早期版本更直接覆盖内容深度、空白、对齐和技术完整性。它的[真实规划提示](https://github.com/Y-Research-SBU/PosterGen/blob/8a54325f871ee10fa6545de3b3a9b771aa12620c/config/prompts/spatial_content_planner.txt)明确要求中间保留核心技术/创新、主方法图，右侧展示结果和比较；[源图分类提示](https://github.com/Y-Research-SBU/PosterGen/blob/8a54325f871ee10fa6545de3b3a9b771aa12620c/config/prompts/classify_visuals.txt)区分 key visual、问题、方法、主结果、比较、支持。其固定三栏与图数属于实现选择，不能强加给所有海报。最终版分别报告内容与审美均分；没有据此编造跨域固定权重。早期 arXiv v1 的 16 项与最终版 20 项分开记录。

## 3. 密度、文字占比、图表占比怎样用才不误判

[内容占用源码](https://github.com/Yaxin9Luo/AutoDesign/blob/bd635851ef8a2ae257e2bf4c8cd4e984ea3fff1e/autodesign/evaluator/spatial.py)不是简单计算非白像素：平色、暗色空洞和噪声不会当作内容；真实纹理、OCR文字和已识别图表范围可以计入；顶部约 14% 标题区域不参与内容占用计算。OCR文字覆盖是识别框面积之和除以整图面积，也不是字形墨水或英文字数占比。

当前评分用内容占用 0.80、OCR框覆盖 0.40 作满分归一化参考，内容权重 0.7，文字只提供额外提升；大空洞会乘性扣分。这是校准参数，不能变成“所有海报必须 80% 填满、40% 文字”。图表内部的白色绘图区可以整个计入内容占用，因此它不等于视觉上的无留白。大学指南要求留白也不能直接拿 `1−0.8` 去比较。

[视觉证据源码](https://github.com/Yaxin9Luo/AutoDesign/blob/bd635851ef8a2ae257e2bf4c8cd4e984ea3fff1e/autodesign/evaluator/metrics.py)输出图表组数量、面积、短边、缩略图组和拼贴提示。图组面积至少 0.15、OCR覆盖至多 0.15 会提示可能是截图墙；靠近的多图高填充簇会提示拼贴。它们都是建议性信号，不能自动否决：稀疏线图、文字表格可能漏检，有意义的多图组合也可能触发提示。最终视觉证据分仍由看图的审稿者判断。

因此应当生成每块的容量预算和证据用途，而非盲目规定总字数或图片总面积。真实源图优先，但选图顺序应同时考虑相关性、解释力、清晰度、美感以及缩放后的可读性；图越多不等于信息越丰富。

## 4. 从生成提示到重建逐块验收

| 检查主题 | 生成前写进提示和计划 | 重建后具体怎么验 |
| --- | --- | --- |
| 内容覆盖 | 每块绑定必须覆盖点和源证据；明确 input、output、model/method、innovation、关键指标 | 按来源逐项查是否真实可见、是否解释充分，数字带任务/基线/单位/限定条件 |
| 密度与综合 | 有实质信息，控制段落，避免空心大卡片；不靠缩字解决容量 | 测内容占用、OCR框、空洞和块字数，同时看全图及局部是否拥挤 |
| 漂亮源图与指标 | 源图分类后优先清晰美观且承担主线的图；方法和结果均获得足够面积 | 查 source ID、完整裁切、轴/图例、旁边 readout、关键指标上下文 |
| 字体与层级 | 少量字体，标题/节标题/正文/图注层级，有限强调 | 测实际计算样式、字体加载、行距与物理字号，截图和打印尺度均查看 |
| 对齐与读序 | 声明网格、共享边缘/基线/内边距，顺着研究逻辑阅读 | DOM查越界/重叠/裁剪/表格；块图查边缘和间距；全图查阅读路径 |
| 背景融合与拼贴 | 让面板底色、源图周边留白协调；避免冲突底纹、阴影和硬贴白图 | 放大看接缝、底色突变、粗边和拥挤图群，再回全图看构图一致性 |
| 配色与对比 | 有来源的主色/过渡色，少量反差强调，同角色颜色一致 | 纯色文字对比可测，复杂背景及图表保真须看图；颜色不能承担唯一语义 |
| 重建/导出 | 生成图实际绘制全部规划证据并给出完整布局，不把合成表格当作数值来源 | 换回原图和真实文字，恢复可编辑表格；查比例、有效分辨率及screen/PDF一致性 |

上表是基于来源的本项目操作化方案，尚未实现的测量不能写成“已通过”。背景融合目前适合归入审美、视觉证据、阅读性并要求可定位的视觉问题；没有证据支持新造一个有固定权重的“融合分”。逐块验收也不能用块均分冒充官方整图 PosterBench，整图要再次检查与评分。

[AutoDesign DOM 审计](https://github.com/Yaxin9Luo/AutoDesign/blob/bd635851ef8a2ae257e2bf4c8cd4e984ea3fff1e/agent_skills/autodesign-poster/scripts/poster_dom_audit.py)已覆盖文字裁剪/重叠、图像有效分辨率、表格字号/溢出、图文间隙、屏幕与打印差异、主画布背景和过度盒子化。其 portable Skill 强制白色主画布，以避免白底源图冲突；这是一项生成合同，不是所有科研海报必须纯白的通用结论。POSFOXGEN若采用图片灵感配色，应明确采用自己的背景合同，同时保留对源图和文字可读性的验收。

## 5. 生成前加入内容 debate

这是用户要求的本项目适配；上述论文支持前置叙事/选图/容量规划，但不能据此声称它们采用同一 debate 方法。

1. 内容规划者先给出问题→输入→方法/模型→输出→关键结果，挑选承担叙事的漂亮源图。
2. 技术反证者对全文追问 input/output/model/innovation、比较基线、评价指标和条件，指出 slogan、遗漏、假逻辑。
3. 视觉规划者核查区块容量、主次、图的缩放与读序；不能以删掉核心技术信息换取整洁。
4. 独立裁决者对照 source span/asset ID 处理争议，记录证据、裁决及计划改动。没有解决的逻辑 blocker 不进入图生成。

保存简洁的争议—证据—裁决—区块改动记录即可，无需保存私有思维链。生成后若发现不能轻修的逻辑错误，返回计划持续重做；不存在第三轮自动放行。重建后逐块复查源证据、数字、逻辑、图文关系，再完成整图和PDF验收。

## 6. 本次 AutoDesign pilot 的主参考

推荐已有库的 **poster-046**：[预览](../data/poster_references/poster-046/preview.png)，[原图](../data/poster_references/poster-046/original.png)。我已实际查看完整预览：左侧动机/贡献，中间概览/方法/公式/环境，右侧实验/消融/过程曲线。该结构适合 AutoDesign 的主链路、组件更新与量化结果并重。只借面积分配、中心方法/右侧指标和读序，不复制文字、logo、研究内容或整组配色；它不是 AutoDesign 自身海报或 Figure 2。源 URL 和哈希见 JSON。

## 7. 数字建议的适用边界

[Paper2Poster Skill 默认](https://github.com/Paper2Poster/Paper2Poster/blob/70fc6f7b778bc8c9bfecc22875eff66f4eb65f93/skills/references/poster-defaults.md)的 250–500 英文字是 48×36 英寸首稿建议。[CU Boulder](https://physicslabs.colorado.edu/posters/design-guide/)针对 47.48×35.61 英寸推荐正文 24–28 pt、图注 20–24 pt、标题 72–96 pt，并强调图像按打印宽度计算分辨率、图表优先矢量。这些是场景建议，不能跨尺寸、中文或不同密度海报直接视为门禁。CSS px、归一化 OCR 像素和物理 pt 也必须分开。[USF](https://guides.lib.usf.edu/ResearchPosters/design-choices)的约 40% 视觉留白属于设计指导，不与内容网格直接等价。
