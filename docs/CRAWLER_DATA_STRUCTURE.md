# MediaCrawlerPro 爬虫数据结构参考文档

> 本文档详细说明所有平台的爬虫类型、数据模型结构，供爬虫 Agent 与云端对接参考。

## 目录

- [通用说明](#通用说明)
- [请求参数结构](#请求参数结构)
- [1. Bilibili (B站)](#1-bilibili-b站)
- [2. Douyin (抖音)](#2-douyin-抖音)
- [3. Kuaishou (快手)](#3-kuaishou-快手)
- [4. Tieba (贴吧)](#4-tieba-贴吧)
- [5. Weibo (微博)](#5-weibo-微博)
- [6. XiaoHongShu (小红书)](#6-xiaohongshu-小红书)
- [7. Zhihu (知乎)](#7-zhihu-知乎)
- [任务调用协议](#任务调用协议)

---

## 通用说明

### 平台代码映射

| 平台 | 平台代码 | 说明 |
|------|----------|------|
| 哔哩哔哩 | `bili` | B站视频平台 |
| 抖音 | `dy` | 短视频平台 |
| 快手 | `ks` | 短视频平台 |
| 百度贴吧 | `tieba` | 论坛社区平台 |
| 微博 | `wb` | 社交媒体平台 |
| 小红书 | `xhs` | 生活方式分享平台 |
| 知乎 | `zhihu` | 问答社区平台 |

### 爬虫类型常量

```python
# 在 constant/base_constant.py 中定义
CRALER_TYPE_SEARCH = 'search'      # 关键词搜索模式
CRALER_TYPE_DETAIL = 'detail'      # 指定内容详情模式
CRALER_TYPE_CREATOR = 'creator'    # 创作者内容模式
CRALER_TYPE_HOMEFEED = 'homefeed'  # 首页推荐流模式
```

### 数据存储方式

所有平台均支持三种存储方式（通过 `SAVE_DATA_OPTION` 配置）：

1. **db** - MySQL 数据库存储（推荐，支持去重）
2. **csv** - CSV 文件存储
3. **json** - JSON 文件存储

### 数据文件命名规则

#### CSV 和 JSON 统一命名格式（已完全统一✅）

**标准格式**（全部 7 个平台）：
```
data/{platform}/{format}/{file_count}_{crawler_type}_{data_type}.{ext}
```

**任务子目录**（当设置 `MC_TASK_ID` 环境变量时）：
```
data/{platform}/{format}/{task_id}/{file_count}_{crawler_type}_{data_type}.{ext}
```

**参数说明**：
- `{platform}`: 平台代码（bili, dy, ks, tieba, wb, xhs, zhihu）
- `{format}`: 数据格式（`csv` 或 `json`）
- `{task_id}`: 任务 ID（数字，如 42、40）
- `{file_count}`: 文件序号（从 1 开始）
- `{crawler_type}`: 爬虫类型（search, detail, creator, homefeed）
- `{data_type}`: 数据类型（contents, comments, creators）
- `{ext}`: 文件扩展名（csv 或 json）

**示例**：

CSV 文件：
- `data/xhs/csv/1_search_contents.csv` (无任务ID)
- `data/dy/csv/42/1_search_comments.csv` (有任务ID)
- `data/bili/csv/40/1_creator_creators.csv` (有任务ID)

JSON 文件：
- `data/xhs/json/1_search_contents.json` (无任务ID)
- `data/dy/json/42/1_search_comments.json` (有任务ID)

**注意**：
- ✅ CSV 和 JSON 文件命名完全统一
- ✅ 都支持任务子目录（通过 `MC_TASK_ID` 环境变量）
- ✅ 文件名都不包含日期后缀
- ✅ 所有平台都包含 `file_count` 序号

### 数据类型分类

每个平台爬取后会生成以下三种数据文件：

1. **contents** - 内容数据（视频、笔记、原文、回答等）
2. **comments** - 评论数据
3. **creators** - 创作者数据

---

## 请求参数结构

> 本章节详细说明下发爬虫任务时需要传递的配置参数结构。

### 通用配置参数

所有爬虫任务都需要的基础配置参数：

| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `PLATFORM` | string | ✅ | 平台代码 | `xhs`, `dy`, `bili`, `ks`, `tieba`, `wb`, `zhihu` |
| `CRAWLER_TYPE` | string | ✅ | 爬虫类型 | `search`, `detail`, `creator`, `homefeed` |
| `SAVE_DATA_OPTION` | string | ✅ | 数据保存格式 | `csv`, `json`, `db` |
| `MAX_CONCURRENCY_NUM` | int | ❌ | 并发数量 | `1`（默认值，建议不要过大） |
| `CRAWLER_MAX_NOTES_COUNT` | int | ❌ | 最大爬取数量 | `20`（默认值） |
| `START_PAGE` | int | ❌ | 起始页码（仅search模式） | `1`（默认值） |
| `ENABLE_GET_COMMENTS` | bool | ❌ | 是否爬取评论 | `true`（默认值） |
| `ENABLE_GET_SUB_COMMENTS` | bool | ❌ | 是否爬取二级评论 | `false`（默认值） |
| `PER_NOTE_MAX_COMMENTS_COUNT` | int | ❌ | 每个原文最大评论数 | `20`（默认值，0表示不限制） |
| `ENABLE_CHECKPOINT` | bool | ❌ | 是否启用断点续爬 | `true`（默认值） |
| `SPECIFIED_CHECKPOINT_ID` | string | ❌ | 指定检查点ID | `""`（空字符串表示加载最新检查点） |
| `CHECKPOINT_STORAGE_TYPE` | string | ❌ | 检查点存储类型 | `file`（可选: `file`, `redis`） |
| `ENABLE_IP_PROXY` | bool | ❌ | 是否启用代理 | `false`（默认值） |
| `CRAWLER_TIME_SLEEP` | int | ❌ | 请求间隔时间（秒） | `2`（默认值） |
| `ACCOUNT_ROTATE_REST_SECONDS` | int | ❌ | 账号轮换休息时长（秒） | `60`（默认值） |

### Search 模式（关键词搜索）

**适用平台**: 全部 7 个平台

**基础参数**:

| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `KEYWORDS` | string | ✅ | 搜索关键词（逗号分隔） | `"苹果,华为"` |
| `START_PAGE` | int | ❌ | 起始页码 | `1` |
| `CRAWLER_MAX_NOTES_COUNT` | int | ❌ | 最大爬取数量 | `20` |

**平台特定参数**:

**小红书 (xhs)**:
| 参数名 | 类型 | 必填 | 说明 | 可选值 |
|--------|------|------|------|--------|
| `SORT_TYPE` | string | ❌ | 排序类型 | `general`（综合）, `popularity_descending`（最热）, `time_descending`（最新） |

**抖音 (dy)**:
| 参数名 | 类型 | 必填 | 说明 | 可选值 |
|--------|------|------|------|--------|
| `PUBLISH_TIME_TYPE` | int | ❌ | 发布时间筛选 | `0`（不限）, `1`（一天内）, `7`（一周内）, `182`（半年内） |

**贴吧 (tieba)** - 额外支持:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `TIEBA_NAME_LIST` | list[string] | ❌ | 指定贴吧名称列表 | `["盗墓笔记"]` |

**配置示例**:

```json
{
  "PLATFORM": "xhs",
  "CRAWLER_TYPE": "search",
  "KEYWORDS": "美食推荐,旅游攻略",
  "SORT_TYPE": "popularity_descending",
  "CRAWLER_MAX_NOTES_COUNT": 50,
  "ENABLE_GET_COMMENTS": true,
  "SAVE_DATA_OPTION": "json"
}
```

### Detail 模式（指定内容详情）

**适用平台**: 全部 7 个平台

每个平台需要指定不同的内容ID或URL列表参数：

**小红书 (xhs)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `XHS_SPECIFIED_NOTE_URL_LIST` | list[string] | ✅ | 笔记URL列表（需包含xsec_token和xsec_source） | `["https://www.xiaohongshu.com/explore/68f20ba9000000000401619f?xsec_token=xxx&xsec_source=pc_feed"]` |

**微博 (wb)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `WEIBO_SPECIFIED_ID_LIST` | list[string] | ✅ | 微博ID列表 | `["5180657661643376"]` |

**贴吧 (tieba)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `TIEBA_SPECIFIED_ID_LIST` | list[string] | ✅ | 原文ID列表 | `["9815127841"]` |

**B站 (bili)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `BILI_SPECIFIED_ID_LIST` | list[string] | ✅ | 视频BVID列表 | `["BV1d54y1g7db", "BV1Sz4y1U77N"]` |

**抖音 (dy)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `DY_SPECIFIED_ID_LIST` | list[string] | ✅ | 视频ID列表 | `["7566756334578830627"]` |

**快手 (ks)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `KS_SPECIFIED_ID_LIST` | list[string] | ✅ | 视频ID列表 | `["3xf8enb8dbj6uig", "3x6zz972bchmvqe"]` |

**知乎 (zhihu)**:
| 参数名 | 类型 | 必填 | 说明 | 支持的URL类型 |
|--------|------|------|------|--------|
| `ZHIHU_SPECIFIED_ID_LIST` | list[string] | ✅ | URL列表 | 回答、文章、视频、问题（见下方说明） |

知乎支持的URL格式：
- 回答: `https://www.zhihu.com/question/{question_id}/answer/{answer_id}`
- 文章: `https://zhuanlan.zhihu.com/p/{article_id}`
- 视频: `https://www.zhihu.com/zvideo/{video_id}`
- 问题: `https://www.zhihu.com/question/{question_id}` （爬取该问题下所有回答，数量由 `CRAWLER_MAX_NOTES_COUNT` 控制）

**配置示例**:

```json
{
  "PLATFORM": "dy",
  "CRAWLER_TYPE": "detail",
  "DY_SPECIFIED_ID_LIST": [
    "7566756334578830627",
    "7525538910311632128"
  ],
  "ENABLE_GET_COMMENTS": true,
  "SAVE_DATA_OPTION": "db"
}
```

### Creator 模式（创作者内容）

**适用平台**: 全部 7 个平台

爬取指定创作者的所有内容及评论。每个平台需要指定不同的创作者ID或URL参数：

**小红书 (xhs)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `XHS_CREATOR_URL_LIST` | list[string] | ✅ | 创作者主页URL（需包含xsec_token和xsec_source） | `["https://www.xiaohongshu.com/user/profile/5f58bd990000000001003753?xsec_token=xxx&xsec_source=pc_search"]` |

**微博 (wb)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `WEIBO_CREATOR_ID_LIST` | list[string] | ✅ | 创作者ID列表 | `["2172061270", "7449968177"]` |

**贴吧 (tieba)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `TIEBA_CREATOR_URL_LIST` | list[string] | ✅ | 创作者主页URL列表 | `["https://tieba.baidu.com/home/main/?id=tb.1.7f139e2e&fr=frs"]` |

**B站 (bili)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `BILI_CREATOR_ID_LIST` | list[string] | ✅ | UP主ID列表 | `["434377496"]` |

**抖音 (dy)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `DY_CREATOR_ID_LIST` | list[string] | ✅ | 创作者Sec ID列表 | `["MS4wLjABAAAATJPY7LAlaa5X-c8uNdWkvz0jUGgpw4eeXIwu_8BhvqE"]` |

**快手 (ks)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `KS_CREATOR_ID_LIST` | list[string] | ✅ | 创作者ID列表 | `["3x4sm73aye7jq7i"]` |

**知乎 (zhihu)**:
| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `ZHIHU_CREATOR_URL_LIST` | list[string] | ✅ | 创作者主页URL列表 | `["https://www.zhihu.com/people/yd1234567"]` |

**配置示例**:

```json
{
  "PLATFORM": "bili",
  "CRAWLER_TYPE": "creator",
  "BILI_CREATOR_ID_LIST": ["434377496"],
  "CRAWLER_MAX_NOTES_COUNT": 100,
  "ENABLE_GET_COMMENTS": true,
  "SAVE_DATA_OPTION": "json"
}
```

### Homefeed 模式（首页推荐流）

**适用平台**: 小红书 (xhs)、抖音 (dy)、B站 (bili)、快手 (ks)、知乎 (zhihu)

**不支持平台**: 微博 (wb)、贴吧 (tieba)

**参数**:

| 参数名 | 类型 | 必填 | 说明 | 示例值 |
|--------|------|------|------|--------|
| `CRAWLER_MAX_NOTES_COUNT` | int | ❌ | 最大爬取数量 | `20` |

**说明**:
- 无需指定额外的搜索词或ID
- 直接爬取当前登录账号的首页推荐内容
- 推荐内容由平台算法决定，每次运行结果可能不同

**配置示例**:

```json
{
  "PLATFORM": "xhs",
  "CRAWLER_TYPE": "homefeed",
  "CRAWLER_MAX_NOTES_COUNT": 50,
  "ENABLE_GET_COMMENTS": true,
  "SAVE_DATA_OPTION": "json"
}
```

### 特殊配置说明

#### 小红书 xsec_token 和 xsec_source

小红书的 `detail` 和 `creator` 模式需要在URL中携带验证参数：

- `xsec_token`: 安全令牌（有时效性）
- `xsec_source`: 来源标识

**获取方式**:
1. 在浏览器中打开小红书网页版
2. 访问目标笔记或创作者主页
3. 从地址栏复制完整URL（包含查询参数）

**示例**:
```
https://www.xiaohongshu.com/explore/68f20ba9000000000401619f?xsec_token=ABFNeBpLwvXZKTnBmYvNWXoooaC0vGY2tSBtjlNNLbYRw=&xsec_source=pc_feed
```

#### 微博全文爬取

微博平台额外提供全文爬取配置：

| 参数名 | 类型 | 必填 | 说明 | 默认值 |
|--------|------|------|------|--------|
| `ENABLE_WEIBO_FULL_TEXT` | bool | ❌ | 是否爬取微博全文 | `false` |

**注意**: 开启后会增加被风控的概率，因为需要对每条微博额外请求详情接口。

#### 账号池配置

系统支持使用账号池来避免单账号频繁请求：

| 参数名 | 类型 | 必填 | 说明 | 可选值 |
|--------|------|------|------|--------|
| `ACCOUNT_POOL_SAVE_TYPE` | string | ✅ | 账号池存储类型 | `EXCEL_ACCOUNT_SAVE`（Excel文件）, `MYSQL_ACCOUNT_SAVE`（MySQL数据库） |

**Excel 格式账号池**:
- 文件路径: `account_pool/{platform}_accounts.xlsx`
- Sheet名称: 平台代码（如 `xhs`, `dy`）
- 列: `account`, `password`, `cookie`, `enable`

---

## 1. Bilibili (B站)

### 平台代码
`bili`

### 支持的爬虫类型

| 类型 | 说明 |
|------|------|
| `search` | 搜索视频并获取评论信息 |
| `detail` | 获取指定视频的详细信息和评论 |
| `creator` | 获取UP主信息及其发布的视频和评论 |
| `homefeed` | 获取首页推荐流视频和评论 |

### 数据模型

#### BilibiliVideo（视频内容）

**文件名模式**: `*_contents_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| video_id | str | 视频ID (aid) |
| bvid | str | 视频ID (bvid) |
| video_type | str | 视频类型 |
| title | str | 视频标题 |
| desc | str | 视频描述 |
| create_time | str | 视频发布时间戳 |
| duration | str | 视频时长 |
| liked_count | str | 视频点赞数 |
| video_play_count | str | 视频播放数量 |
| video_danmaku | str | 视频弹幕数量 |
| video_comment | str | 视频评论数量 |
| video_url | str | 视频详情URL |
| video_cover_url | str | 视频封面图URL |
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像地址 |
| source_keyword | str | 搜索来源关键字 |
| add_ts | int | 记录添加时间戳 |
| last_modify_ts | int | 记录最后修改时间戳 |

#### BilibiliComment（评论）

**文件名模式**: `*_comments_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| comment_id | str | 评论ID |
| video_id | str | 视频ID |
| content | str | 评论内容 |
| create_time | str | 评论时间戳 |
| sub_comment_count | str | 评论回复数 |
| like_count | str | 点赞数 |
| parent_comment_id | str | 父评论ID |
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像地址 |
| add_ts | int | 记录添加时间戳 |
| last_modify_ts | int | 记录最后修改时间戳 |

#### BilibiliUpInfo（UP主信息）

**文件名模式**: `*_creators_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像地址 |
| description | str | 用户描述 |
| follower_count | str | 粉丝数 |
| following_count | str | 关注数 |
| content_count | str | 作品数 |
| add_ts | int | 记录添加时间戳 |
| last_modify_ts | int | 记录最后修改时间戳 |

---

## 2. Douyin (抖音)

### 平台代码
`dy`

### 支持的爬虫类型

| 类型 | 说明 |
|------|------|
| `search` | 搜索视频并获取评论信息 |
| `detail` | 获取指定视频的详细信息和评论 |
| `creator` | 获取创作者信息及其发布的视频和评论 |
| `homefeed` | 获取首页推荐流视频和评论 |

### 数据模型

#### DouyinAweme（视频内容）

**文件名模式**: `*_contents_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| aweme_id | str | 视频ID |
| aweme_type | str | 视频类型 |
| title | str | 视频标题 |
| desc | str | 视频描述 |
| create_time | str | 视频发布时间戳 |
| liked_count | str | 视频点赞数 |
| comment_count | str | 视频评论数 |
| share_count | str | 视频分享数 |
| collected_count | str | 视频收藏数 |
| aweme_url | str | 视频详情页URL |
| cover_url | str | 视频封面图URL |
| video_download_url | str | 视频下载地址 |
| source_keyword | str | 搜索来源关键字 |
| is_ai_generated | int | 作者是否声明视频为AI生成 |
| user_id | str | 用户ID |
| sec_uid | str | 用户sec_uid |
| short_user_id | str | 用户短ID |
| user_unique_id | str | 用户唯一ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像地址 |
| user_signature | str | 用户签名 |
| ip_location | str | IP地址 |

#### DouyinAwemeComment（评论）

**文件名模式**: `*_comments_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| comment_id | str | 评论ID |
| aweme_id | str | 视频ID |
| content | str | 评论内容 |
| create_time | str | 评论时间戳 |
| sub_comment_count | str | 评论回复数 |
| parent_comment_id | str | 父评论ID |
| reply_to_reply_id | str | 目标评论ID |
| like_count | str | 点赞数 |
| pictures | str | 评论图片列表 |
| ip_location | str | 评论时的IP地址 |
| user_id | str | 用户ID |
| sec_uid | str | 用户sec_uid |
| short_user_id | str | 用户短ID |
| user_unique_id | str | 用户唯一ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像地址 |
| user_signature | str | 用户签名 |

#### DouyinCreator（创作者信息）

**文件名模式**: `*_creators_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像地址 |
| ip_location | str | IP地址 |
| desc | str | 用户描述 |
| gender | str | 性别 |
| follows | str | 关注数 |
| fans | str | 粉丝数 |
| interaction | str | 获赞数 |
| videos_count | str | 作品数 |

---

## 3. Kuaishou (快手)

### 平台代码
`ks`

### 支持的爬虫类型

| 类型 | 说明 |
|------|------|
| `search` | 搜索视频并获取评论信息 |
| `detail` | 获取指定视频的详细信息和评论 |
| `creator` | 获取创作者信息及其发布的视频和评论 |
| `homefeed` | 获取首页推荐流视频和评论 |

### 数据模型

#### KuaishouVideo（视频内容）

**文件名模式**: `*_contents_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| video_id | str | 视频ID |
| video_type | str | 视频类型 |
| title | str | 视频标题 |
| desc | str | 视频描述 |
| create_time | str | 创建时间戳 |
| liked_count | str | 点赞数 |
| viewd_count | str | 观看数 |
| video_url | str | 视频详情页URL |
| video_cover_url | str | 视频封面图URL |
| video_play_url | str | 视频播放URL |
| source_keyword | str | 搜索来源关键字 |
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像地址 |

#### KuaishouVideoComment（评论）

**文件名模式**: `*_comments_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| comment_id | str | 评论ID |
| parent_comment_id | str | 父评论ID |
| video_id | str | 视频ID |
| content | str | 评论内容 |
| create_time | str | 评论时间戳 |
| sub_comment_count | str | 子评论数 |
| like_count | str | 点赞数 |
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像地址 |

#### KuaishouCreator（创作者信息）

**文件名模式**: `*_creators_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像地址 |
| gender | str | 性别 |
| desc | str | 个人简介 |
| ip_location | str | IP地理位置 |
| follows | str | 关注数 |
| fans | str | 粉丝数 |
| videos_count | str | 作品数 |

---

## 4. Tieba (贴吧)

### 平台代码
`tieba`

### 支持的爬虫类型

| 类型 | 说明 |
|------|------|
| `search` | 搜索原文并获取评论信息 |
| `detail` | 获取指定原文的详细信息和评论 |
| `creator` | 获取创作者信息及其发布的原文和评论 |

### 数据模型

#### TiebaNote（原文内容）

**文件名模式**: `*_contents_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| note_id | str | 原文ID（必填） |
| title | str | 原文标题（必填） |
| desc | str | 原文描述 |
| note_url | str | 原文链接（必填） |
| publish_time | str | 发布时间 |
| user_link | str | 用户主页链接 |
| user_nickname | str | 用户昵称 |
| user_avatar | str | 用户头像地址 |
| tieba_name | str | 贴吧名称（必填） |
| tieba_link | str | 贴吧链接（必填） |
| total_replay_num | int | 回复总数 |
| total_replay_page | int | 回复总页数 |
| ip_location | str | IP地理位置 |
| source_keyword | str | 来源关键词 |

#### TiebaComment（评论）

**文件名模式**: `*_comments_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| comment_id | str | 评论ID（必填） |
| parent_comment_id | str | 父评论ID |
| content | str | 评论内容（必填） |
| user_link | str | 用户主页链接 |
| user_nickname | str | 用户昵称 |
| user_avatar | str | 用户头像地址 |
| publish_time | str | 发布时间 |
| ip_location | str | IP地理位置 |
| sub_comment_count | int | 子评论数 |
| note_id | str | 原文ID（必填） |
| note_url | str | 原文链接（必填） |
| tieba_id | str | 所属的贴吧ID（必填） |
| tieba_name | str | 所属的贴吧名称（必填） |
| tieba_link | str | 贴吧链接（必填） |

#### TiebaCreator（创作者信息）

**文件名模式**: `*_creators_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| user_id | str | 用户ID（必填） |
| user_name | str | 用户名（必填） |
| nickname | str | 用户昵称（必填） |
| gender | str | 用户性别 |
| avatar | str | 用户头像地址（必填） |
| ip_location | str | IP地理位置 |
| follows | int | 关注数 |
| fans | int | 粉丝数 |
| registration_duration | str | 注册时长 |

---

## 5. Weibo (微博)

### 平台代码
`wb`

### 支持的爬虫类型

| 类型 | 说明 |
|------|------|
| `search` | 搜索笔记并获取评论信息 |
| `detail` | 获取指定笔记的详细信息和评论 |
| `creator` | 获取创作者信息及其发布的笔记和评论 |

### 数据模型

#### WeiboNote（笔记内容）

**文件名模式**: `*_contents_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| note_id | str | 笔记ID |
| content | str | 笔记内容 |
| create_time | str | 创建时间戳 |
| create_date_time | str | 创建日期时间 |
| liked_count | str | 点赞数 |
| comments_count | str | 评论数 |
| shared_count | str | 转发数 |
| note_url | str | 笔记URL |
| ip_location | str | IP地理位置 |
| image_list | str | 图片列表 |
| video_url | str | 视频URL |
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| gender | str | 用户性别 |
| profile_url | str | 用户主页URL |
| avatar | str | 用户头像 |
| source_keyword | str | 搜索来源关键字 |
| add_ts | int | 记录添加时间戳 |
| last_modify_ts | int | 记录最后修改时间戳 |

#### WeiboComment（评论）

**文件名模式**: `*_comments_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| comment_id | str | 评论ID |
| note_id | str | 笔记ID |
| content | str | 评论内容 |
| create_time | str | 创建时间戳 |
| create_date_time | str | 创建日期时间 |
| sub_comment_count | str | 子评论数 |
| like_count | str | 点赞数 |
| ip_location | str | IP地理位置 |
| parent_comment_id | str | 父评论ID |
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| gender | str | 用户性别 |
| profile_url | str | 用户主页URL |
| avatar | str | 用户头像 |
| add_ts | int | 记录添加时间戳 |
| last_modify_ts | int | 记录最后修改时间戳 |

#### WeiboCreator（创作者信息）

**文件名模式**: `*_creators_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| gender | str | 性别 |
| avatar | str | 头像 |
| desc | str | 用户描述 |
| ip_location | str | IP地理位置 |
| follows | str | 关注数 |
| fans | str | 粉丝数 |
| tag_list | str | 标签列表 |
| add_ts | int | 记录添加时间戳 |
| last_modify_ts | int | 记录最后修改时间戳 |

---

## 6. XiaoHongShu (小红书)

### 平台代码
`xhs`

### 支持的爬虫类型

| 类型 | 说明 |
|------|------|
| `search` | 搜索笔记并获取评论信息 |
| `detail` | 获取指定笔记的详细信息和评论 |
| `creator` | 获取创作者信息及其发布的笔记和评论 |
| `homefeed` | 获取首页推荐流笔记和评论 |

### 数据模型

#### XhsNote（笔记内容）

**文件名模式**: `*_contents_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| note_id | str | 笔记ID |
| type | str | 笔记类型(normal \| video) |
| title | str | 笔记标题 |
| desc | str | 笔记描述 |
| video_url | str | 视频链接 |
| time | str | 发布时间戳 |
| last_update_time | str | 最后更新时间戳 |
| ip_location | str | IP地理位置 |
| image_list | str | 图片链接列表，逗号分隔 |
| tag_list | str | 标签列表，逗号分隔 |
| note_url | str | 笔记链接 |
| source_keyword | str | 来源关键词 |
| liked_count | str | 点赞数 |
| collected_count | str | 收藏数 |
| comment_count | str | 评论数 |
| share_count | str | 分享数 |
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像 |

#### XhsComment（评论）

**文件名模式**: `*_comments_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| comment_id | str | 评论ID |
| parent_comment_id | str | 父评论ID |
| target_comment_id | str | 目标评论ID（回复某条评论） |
| note_id | str | 笔记ID |
| content | str | 评论内容 |
| create_time | str | 创建时间戳 |
| ip_location | str | IP地理位置 |
| sub_comment_count | str | 子评论数 |
| like_count | str | 点赞数 |
| pictures | str | 图片链接列表，逗号分隔 |
| note_url | str | 笔记链接 |
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像 |

#### XhsCreator（创作者信息）

**文件名模式**: `*_creators_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| user_id | str | 用户ID |
| nickname | str | 用户昵称 |
| avatar | str | 用户头像 |
| gender | str | 性别 |
| desc | str | 个人简介 |
| ip_location | str | IP地理位置 |
| follows | str | 关注数 |
| fans | str | 粉丝数 |
| interaction | str | 互动数 |
| tag_list | str | 标签列表，JSON字符串 |

---

## 7. Zhihu (知乎)

### 平台代码
`zhihu`

### 支持的爬虫类型

| 类型 | 说明 |
|------|------|
| `search` | 搜索内容（回答、文章、视频）并获取评论信息 |
| `detail` | 获取指定内容的详细信息和评论（支持回答、文章、视频、问题下的所有回答） |
| `creator` | 获取创作者信息及其发布的内容和评论 |
| `homefeed` | 获取首页推荐流内容和评论 |

### 数据模型

#### ZhihuContent（内容数据）

**文件名模式**: `*_contents_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| content_id | str | 内容ID |
| content_type | str | 内容类型(article \| answer \| zvideo) |
| content_text | str | 内容文本（视频类型时为空） |
| content_url | str | 内容落地链接 |
| question_id | str | 问题ID（类型为answer时有值） |
| title | str | 内容标题 |
| desc | str | 内容描述 |
| created_time | int | 创建时间 |
| updated_time | int | 更新时间 |
| voteup_count | int | 赞同人数 |
| comment_count | int | 评论数量 |
| source_keyword | str | 来源关键词 |
| user_id | str | 用户ID |
| user_link | str | 用户主页链接 |
| user_nickname | str | 用户昵称 |
| user_avatar | str | 用户头像地址 |
| user_url_token | str | 用户url_token |

#### ZhihuComment（评论）

**文件名模式**: `*_comments_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| comment_id | str | 评论ID |
| parent_comment_id | str | 父评论ID |
| content | str | 评论内容 |
| publish_time | int | 发布时间 |
| ip_location | str | IP地理位置 |
| sub_comment_count | int | 子评论数 |
| like_count | int | 点赞数 |
| dislike_count | int | 踩数 |
| content_id | str | 内容ID |
| content_type | str | 内容类型(article \| answer \| zvideo) |
| user_id | str | 用户ID |
| user_link | str | 用户主页链接 |
| user_nickname | str | 用户昵称 |
| user_avatar | str | 用户头像地址 |

#### ZhihuCreator（创作者信息）

**文件名模式**: `*_creators_*.{csv|json}`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| user_id | str | 用户ID |
| user_link | str | 用户主页链接 |
| user_nickname | str | 用户昵称 |
| user_avatar | str | 用户头像地址 |
| url_token | str | 用户url_token |
| gender | str | 用户性别 |
| ip_location | str | IP地理位置 |
| follows | int | 关注数 |
| fans | int | 粉丝数 |
| anwser_count | int | 回答数 |
| video_count | int | 视频数 |
| question_count | int | 提问数 |
| article_count | int | 文章数 |
| column_count | int | 专栏数 |
| get_voteup_count | int | 获得的赞同数 |

---

## 任务调用协议

> 早期版本曾规划 WebSocket 推送模型，**从未实现**。实际采用 HTTP 轮询（Agent pull）：
> Agent 轮询 `GET /api/v1/agent/tasks/pending` 认领任务 → 执行采集 → 上报进度与结果。
> 完整接口契约（含 phase、去重幂等、上传格式）见 [`docs/云端分析平台API规范.md`](./云端分析平台API规范.md)。

---

## 附录

### 平台特性差异

| 平台 | homefeed | 视频下载URL | IP位置 | AI生成标识 |
|------|----------|-------------|--------|------------|
| Bilibili | ✓ | ✗ | ✗ | ✗ |
| Douyin | ✓ | ✓ | ✓ | ✓ |
| Kuaishou | ✓ | ✓ | ✓ | ✗ |
| Tieba | ✗ | ✗ | ✓ | ✗ |
| Weibo | ✗ | ✓ | ✓ | ✗ |
| XiaoHongShu | ✓ | ✓ | ✓ | ✗ |
| Zhihu | ✓ | ✗ | ✓ | ✗ |

### 数据字段命名约定

1. **ID 类字段**：统一使用 `_id` 后缀（如 `user_id`, `note_id`, `comment_id`）
2. **计数类字段**：统一使用 `_count` 后缀（如 `liked_count`, `fans_count`）
3. **URL 类字段**：统一使用 `_url` 后缀（如 `note_url`, `video_url`）
4. **时间类字段**：
   - 时间戳：`create_time`, `publish_time`
   - 格式化时间：`create_date_time`
   - 时间戳（记录级）：`add_ts`, `last_modify_ts`
5. **列表类字段**：统一使用 `_list` 后缀（如 `image_list`, `tag_list`）

### 实现不一致性说明

在当前实现中存在以下不一致性，使用时需要注意：

#### 1. Creator 文件命名（已统一✅）

**所有平台已统一使用复数形式 `creators`**：

| 平台 | CSV 文件后缀 | JSON 文件后缀 |
|------|-------------|--------------|
| Bilibili | `_creators_*.csv` | `_creators.json` |
| Douyin | `_creators_*.csv` | `_creators.json` |
| Kuaishou | ⚠️ 不支持 CSV | `_creators.json` |
| Tieba | `_creators_*.csv` | `_creators.json` |
| Weibo | `_creators_*.csv` | `_creators.json` |
| XiaoHongShu | `_creators_*.csv` | `_creators.json` |
| Zhihu | `_creators_*.csv` | `_creators.json` |

**说明**：
- ✅ 所有平台统一使用复数形式 `creators`，与 `contents`、`comments` 保持一致
- ⚠️ Kuaishou 平台的 CSV 存储未实现 creator 导出功能

#### 2. CSV 文件命名格式差异

- **Weibo**: `{crawler_type}_{data_type}_{date}.csv` (无 file_count 序号)
- **其他平台**: `{file_count}_{crawler_type}_{data_type}_{date}.csv` (有 file_count 序号)

#### 3. 日期后缀差异

- **CSV 文件**: 包含日期后缀 `_20240114.csv`
- **JSON 文件**: 不包含日期后缀 `.json`

### 常见问题

**Q: 为什么有的平台字段类型都是 str，即使是数字？**

A: 为了保持数据的一致性和避免类型转换问题，大部分数值型字段都存储为字符串。在使用时可根据需要进行类型转换。

**Q: 如何处理子评论？**

A: 子评论会被展开为独立的评论记录，通过 `parent_comment_id` 字段关联父评论。

**Q: 数据去重如何实现？**

A: 使用数据库存储时（`SAVE_DATA_OPTION=db`），会根据主键自动去重。文件存储模式不支持自动去重。

**Q: 如何获取任务的实时进度？**

A: Agent 通过 HTTP 轮询认领任务并定期上报进度（见 `docs/云端分析平台API规范.md`）。

**Q: 为什么 Kuaishou CSV 不支持 creator 导出？**

A: 这是当前实现的限制。如需导出快手创作者数据，请使用 JSON 或 DB 存储方式。

---

**文档版本**: v1.2
**最后更新**: 2025-11-11
**维护者**: crawler-agent 团队
**变更记录**: v1.2 - 统一所有平台 creator 命名为 creators (复数形式)
