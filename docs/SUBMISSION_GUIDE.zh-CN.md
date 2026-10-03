# 源码与结果提交指南

## 交付内容

本仓库包含源码、配置、依赖锁定文件、数据来源、已有结果及评估记录。
模型身份与可用文件见 [MODEL_CARD.md](../MODEL_CARD.md)，评估解释见
[EVIDENCE_SUMMARY.md](EVIDENCE_SUMMARY.md)。

2026 年 9 月 17 日的[官方第二轮通知](https://competition.openlifesci-alliance.org/home/newsDetails?newsId=131383)
附件5要求提供运行环境、源代码、适用的模型文件或调用说明、运行入口、示例和来源记录。
目录名称不是固定要求；功能等效的入口应在 README 中给出完整命令。

## 安装与检查

Python ≥3.11。CPU 可完成软件示例、已有结果导出及完整性检查。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m aav9_sma demo --output-dir artifacts/demo
PYTHONPATH=src python scripts/verify_submission.py
```

该安装方式采用兼容依赖范围。已安装 uv 的环境可用 `uv sync --frozen --extra dev`
按锁文件安装。`requirements.txt` 是兼容范围，`uv.lock` 是解析后的依赖锁文件。
合成示例用于软件接口检查，不加载历史模型。

## 已有结果的审计与导出

```bash
PYTHONPATH=src python scripts/prepare_submission.py
PYTHONPATH=src python scripts/verify_submission.py
```

第一条命令会更新结果导出、审计记录和清单；第二条只核验文件。
这些命令读取已有结果，不执行模型训练或新的预测。

| 输出 | 用途 |
| --- | --- |
| `results/results.csv` | 已有结果的标准化导出 |
| `results/results_manifest.json` | 结果版本与来源校验值 |
| `docs/audit_data/updated_7_0/` | 逐终点评估与证据报告 |
| `logs/submission_audit_run.json` | 本次导出执行环境、耗时及代码校验值 |
| `logs/final_model_record.json` | 从历史记录恢复的训练信息 |
| `docs/submission_manifest.json` | 源码与交付文件校验清单 |

修改受校验文件后，应重新审计并检查差异，再提交更新后的清单。
历史训练记录与本次导出执行记录分别保存。

## 尚未完成的交付项

| 项目 | 当前状态 |
| --- | --- |
| 历史模型权重和同期训练日志 | 未留存；已有结果及恢复的参数记录不能替代权重 |
| 正式候选结果模板 | 通用字段要求已查阅；赛道专用模板尚未核对 |
| 项目再分发许可 | 尚未确定，见 [LICENSE_STATUS.md](../LICENSE_STATUS.md) |

`verify_submission.py` 的 `integrity_ok` 表示文件一致性，`submission_ready`
表示已声明缺项是否清零。`--require-ready` 在存在缺项时返回非零退出码。
应根据已补齐的实际文件更新状态，不应仅删除缺项文字。

## 数据与环境记录

- 数据来源和上游版本：[source_manifest.json](source_manifest.json)。
- 本次核对的输入文件哈希：[data_manifest.json](data_manifest.json)。
- 输入输出字段：[DATA_CONTRACT.md](DATA_CONTRACT.md)。
- 环境记录：`logs/audit_environment_requirements.txt` 为审计环境快照。
- 第三方来源：[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

原始研究数据单独获取，不随源码包重新分发。完整计算所需的峰值内存、磁盘和耗时
尚未在当前交付版本重新测量；审计导出的耗时仅对应审计操作。

## 打包

完成修改、运行校验并提交文件后：

```bash
python scripts/package_submission.py --output submission_packages/source.zip
```

脚本从当前提交读取文件，检查其交付清单，生成带 `PACKAGE_MANIFEST.json` 的 ZIP。
打包时排除 Git 历史、未跟踪文件、个人环境、缓存和录屏文件。
压缩包内的清单记录来源提交、每个文件的 SHA256 和尚未完成的交付项。

仅允许就绪版本时：

```bash
python scripts/package_submission.py --require-ready --output submission_packages/source.zip
```

该选项检查仓库已声明的缺项，不代替主办方对完整提交材料的审核。
代码录屏按附件6单独准备：自愿提交，建议不超过10分钟，单独视频不超过50 MB，
或插入汇报PPT。PPT台词录音另受附件4的8分钟限制。
