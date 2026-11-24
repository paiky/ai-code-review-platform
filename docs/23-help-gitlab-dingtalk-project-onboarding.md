# GitLab / 钉钉 / 项目接入

> 状态说明：本文是面向内部环境的接入帮助页文档源。Webhook URL 示例 `http://ai-review.ihere.net` 需替换为你实际部署的平台地址；通用步骤亦见 `docs/18-project-integration-user-guide.md`。

## 一、配置 GitLab Webhook

进入需要接入的平台项目：

```text
GitLab 项目 -> Settings -> Webhooks
```

Webhook URL 固定填写：

```text
http://ai-review.ihere.net/api/webhooks/gitlab/merge-request
```

打勾：

```text
Merge request events
```

```text
Push events
```

Secret Token 保持为空即可。

![image-20260527110201878](https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/deadbf05a7ea499198d905a5f4c0cb74.png)

保存后可以点击 GitLab 的测试按钮确认平台是否能收到请求。

## 二、配置钉钉机器人

在用于接收审查结果的钉钉群中创建机器人：

```text
群设置 -> 机器人 -> 添加机器人 -> 自定义机器人
```

安全设置选择关键词，并填写：

```text
变更审查结果
```

也可以选择公网 IP 段白名单，但平台出口 IP 可能随网络、部署或云资源调整而变化，后续维护成本更高。

创建完成后，钉钉会生成机器人 Webhook URL。拿到 URL 后，只在平台“设置”页中配置。

![image-20260527110201878](https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/image-20260527110201878.png)

## 三、维护钉钉机器人库

进入平台：

```text
设置 -> 项目 / 端类型配置 -> 钉钉机器人库
```

录入从钉钉复制的 Webhook URL，保存并启用机器人。

## 四、配置 GitLab 项目

平台可从首个满足条件的 Webhook 自动创建项目。需要提前配置时，使用 [项目创建 API](03-api-contract.md#42-创建项目接入配置)。在「项目 / 端类型配置 → 项目配置」编辑项目，确认所属端、Profile、审查范围、MR/Push 触发设置，并关联已启用的机器人。通知按项目关联发送，项目没有可用机器人时会记录为跳过。

## 五、配置模型 Provider 和默认模型

如果项目只需要规则提醒和钉钉通知，可以先跳过模型配置。启用 AI Review 时，在「设置 → AI Review 配置」维护模型连接和审查策略，并到「项目配置」确认 Profile 与对应触发开关。

```text
Provider 已启用
API Key 已填写
Endpoint URL 已填写
Model 名称已填写
点击“测试连接”确认模型服务可访问
全局默认 Provider 已设置
```

当前内置 Provider 包括 OpenAI、Anthropic、DeepSeek、XiaoMIMO、GLM 和自定义 OpenAI-compatible。「测试连接」会使用当前表单中的端点、模型名称和临时输入的 API Key 发起一次最小请求，临时 Key 不会被保存。
