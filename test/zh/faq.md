

# MetaGPT-Index / 常见问题解答（FAQ）

> 我们的愿景是[延长人类寿命](https://github.com/geekan/HowToLiveLonger)并[减少工作时长](https://github.com/geekan/MetaGPT/)。

### 文档分享快捷链接

```
https://docs.deepwisdom.ai/main/en/guide/faq.html
https://docs.deepwisdom.ai/main/zh/guide/faq.html
```

### 相关链接

1. 代码仓库：https://github.com/geekan/MetaGPT
2. 路线图：https://github.com/geekan/MetaGPT/blob/main/docs/ROADMAP.md
3. 英文资源
    1. 演示视频：[MetaGPT: Multi-Agent AI Programming Framework](https://www.youtube.com/watch?v=8RNzxZBTW8M)
    2. 教程：[MetaGPT: Deploy POWERFUL Autonomous Ai Agents BETTER Than SUPERAGI!](https://www.youtube.com/watch?v=q16Gi9pTG_M&t=659s)
    3. 作者观点视频（英文）：[MetaGPT Matthew Berman](https://youtu.be/uT75J_KG_aY?si=EgbfQNAwD8F5Y1Ak)
4. 中文资源
    1. 演示视频：[MetaGPT：一行代码搭建你的虚拟公司_哔哩哔哩_bilibili](https://www.bilibili.com/video/BV1NP411C7GW/?spm_id_from=333.999.0.0&vd_source=735773c218b47da1b4bd1b98a33c5c77)
    2. 教程：[一个提示词写游戏 Flappy bird, 比AutoGPT强10倍的MetaGPT，最接近AGI的AI项目](https://youtu.be/Bp95b8yIH5c)
    3. 作者观点视频（中文）：[MetaGPT作者深度解析直播回放_哔哩哔哩_bilibili](https://www.bilibili.com/video/BV1Ru411V7XL/?spm_id_from=333.337.search-card.all.click)



### 首席布道师（月度轮值）

MetaGPT社区首席布道师实行月度轮换制，主要职责包括：

1. 维护社区FAQ文档、公告及GitHub资源/README
2. 平均30分钟内响应、解答并分流社区问题（包括GitHub Issues、Discord和微信等平台）
3. 维护热情、真诚、友好的社区氛围
4. 鼓励成员成为贡献者，参与与实现AGI（通用人工智能）密切相关的项目
5. （可选）组织黑客松等小型活动

### 常见问题解答

1. **生成仓库代码体验**：
   - 示例参见[MetaGPT Release v0.1.0](https://github.com/geekan/MetaGPT/releases/tag/v0.1.0)

2. **代码截断/解析失败**：
   - 检查长度是否过长，建议使用gpt-3.5-turbo-16k或更高token限额的模型

3. **成功率**：
   - 暂无量化统计，但GPT-4的代码生成成功率显著高于gpt-3.5-turbo

4. **是否支持增量或差异更新（如续作半成品）？**：
   - 支持，详见[增量开发指南](https://docs.deepwisdom.ai/main/en/guide/in_depth_guides/incremental_development.html)

5. **是否支持加载现有代码？**：
   - 当前不在路线图中，但已规划相关功能，需时间实现

6. **是否支持多编程语言和自然语言？**：
   - 已在[路线图](https://github.com/geekan/MetaGPT/blob/main/docs/ROADMAP.md)中规划，部分已支持

7. **如何加入贡献者团队？**：
   - 提交PR即可加入，当前工作重点参见[路线图](https://github.com/geekan/MetaGPT/blob/main/docs/ROADMAP.md)

8. **PRD卡住/无法访问/连接中断**：
   - 官方`OPENAI_API_BASE`端点为`https://api.openai.com/v1`
   - 若环境中无法访问官方地址（可用curl验证），建议使用[openai-forward](https://github.com/beidongjiedeguang/openai-forward)等反向代理，设置`OPENAI_API_BASE`为`https://api.openai-forward.com/v1`
   - 或通过配置`OPENAI_PROXY`使用本地代理访问官方端点，不需要时代理需关闭。正确配置示例：`OPENAI_API_BASE: "https://api.openai.com/v1"`
   - 持续网络问题可尝试云环境，如[MetaGPT快速体验](https://deepwisdom.feishu.cn/wiki/Q8ycw6J9tiNXdHk66MRcIN8Pnlg)


9.  **稳定支持的Python版本**：
    - Python 3.9和3.10

10. **GPT-4不可用/模型未找到（`The model gpt-4 does not exist`）**：
    - OpenAI要求至少消费$1才能访问GPT-4。在使用免费额度后运行少量gpt-3.5-turbo任务通常可解锁GPT-4访问

11. **能否生成未见过游戏的代码？**：
    - 如README所述，可生成复杂系统（如类似TikTok的推荐系统）的建议或代码，提示词示例："Write a recommendation system like TikTok’s"

12. **常见错误场景**：
    - 超过500行代码：部分函数可能未实现
    - 数据库使用：代码缺少SQL DB初始化常导致错误
    - 大型代码库可能出现幻觉，如调用不存在API

13. **SD技能使用说明**：
    - SD技能为可调用工具，通过`SDEngine`实例化（见`metagpt/tools/libs/sd_engine.py`）
    - 部署细节参考[stable-diffusion-webui](https://github.com/AUTOMATIC1111/stable-diffusion-webui)，例如：
      1. `python webui.py --enable-insecure-extension-access --port xxx --no-gradio-queue --nowebui`
      2. 模型加载后（约1分钟）访问SD服务，设置`sd_url`为`IP:Port`（默认7860）


14. **openai.error.RateLimitError**：
    - 若仍有免费额度，设置`RPM`为3或更低
    - 额度耗尽建议升级付费计划

15. **`n_borg`中borg含义**：
    - 源自[维基百科博格文明](https://en.wikipedia.org/wiki/Borg)，指集体意识

16. **如何使用Claude API？**：
    - 在`config2.yaml`中配置`llm`，详见[Claude API配置](https://docs.deepwisdom.ai/main/zh/guide/get_started/configuration/llm_api_configuration.html#anthropic-claude-api)


17. **Tenacity重试错误（`RetryError`）**：
    - 网络解决方案参考FAQ #8
    - 使用`gpt-3.5-turbo-16k`或`gpt-4`模型，技术细节参见[GitHub Issue #117](https://github.com/geekan/MetaGPT/issues/117)

### 参考

1. [0723-MetaGPT使用指南](https://deepwisdom.feishu.cn/docx/A0abdLlZJogwsRxjkQucifVinsd)