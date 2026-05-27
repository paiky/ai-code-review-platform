# GitLab / 钉钉 / 项目组接入

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

## 三、配置平台项目组

进入平台：

```text
设置 -> 项目组 / 端类型配置
```

先创建或复用已有项目组。项目组通常按业务线、团队或产品域划分，用于：

```text
归类多个 GitLab 项目
筛选任务列表
配置项目组钉钉机器人
配置默认 AI Review Profile
配置默认模型 Provider
维护 Push 审核策略
```

给项目组配置钉钉机器人时，把上一步从钉钉复制的 Webhook URL 填入该项目组的机器人配置，并启用它。平台会优先按项目所属项目组发送通知。

![image-20260527110201878](https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/screenshot_2026-05-27_11-10-57.png)

## 四、配置GitLab 项目

首次收到某个 GitLab 项目的 Webhook 后，平台可以自动创建项目记录。自动创建的项目会进入默认项目组，后续可以再人工调整。

![image-20260527110201878](https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/cd00250a14cb455e95f79c07f7cd6a03.png)

## 五、配置模型 Provider 和默认模型

如果项目只需要规则提醒和钉钉通知，可以先跳过模型配置。需要启用代码质量 AI Review 时，先在设置页配置全局 Provider，再为项目组选择默认 AI Review Profile 和默认 Provider。

![image-20260527112725](https://seeworld-internal-gn.oss-cn-beijing.aliyuncs.com/images/temp/screenshot_2026-05-27_11-27-25.png)
