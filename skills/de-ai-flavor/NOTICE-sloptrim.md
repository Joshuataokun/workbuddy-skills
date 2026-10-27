# 第三方声明

本技能的 `scripts/deai_check.py` 在以下方面移植自 sloptrim：

- 文件位置：https://github.com/seyedehsanhadi/sloptrim
- 作者：seyedehsanhadi
- 许可证：Apache License 2.0（全文见同目录 `LICENSE-sloptrim.txt`）
- 移植内容：0–100 打分架构（内容族多样性 + 密度 + 节奏项 + 词表密度 + 决定性模式升级地板）、五档分级、Office 文件（docx/pptx/xlsx/odt/ods）zip + ElementTree 文本抽取思路、成员大小上限与解析容错。

**未移植**：sloptrim 的 71 条英文模式词表及其检测器、README 所载基准测试与数据集、hook 与插件安装层。中文规则库为本技能重写，与 sloptrim 原规则不存在一一对应关系。

原项目版权归其作者所有，本项目对其移植部分的修改同样以 Apache-2.0 提供。

## 中文规则来源

- [qu-ai-wei](https://github.com/LifelongLazyLearner/qu-ai-wei)（MIT）：中文症状分类、「骨架/触发/保护/动作/复扫」结构、证据等级做法。
- [blader/humanizer](https://github.com/blader/humanizer)（MIT）与维基百科《Signs of AI writing》：英文侧原始症状清单，本技能已按中文重写。

## PPT 版式判据

本技能的「一页一个阅读方向」判据由项目使用者提出并定义，不是上述任何开源项目的既有规则。
