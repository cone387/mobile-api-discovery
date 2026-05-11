# 河马漫剧 API 接口报告

## 数据链路

```
剧场分类列表 (/portal/1125)
  │  返回 columnData[].videoData[]: [{bookId, bookName, coverBottomTips(播放量), videoStarsNum(点赞), coverWap(封面), bookTags...}]
  │  ✅ 含播放量（coverBottomTips 字段，如 "7.5亿播放"）
  │  分页: pageFlag + hasMore
  │
  ▼
短剧详情+剧集列表 (/portal/1131)
  │  请求: {bookId}
  │  返回: videoInfo(短剧完整信息) + chapterList(全部剧集列表) + content.mp4Url(当前集播放地址)
  │
  ▼
切集播放 (/portal/1139)
  │  请求: {bookId, chapterIds, chapterId}
  │  返回: chapterInfo[](指定集的播放地址 + 评论数)
  │

```

## 关键字段对照

| 字段 | 含义 | 所在接口 | 示例 |
|------|------|----------|------|
| `coverBottomTips` | **播放量**（页面展示值） | /portal/1125 | "7.5亿播放" |
| `videoStarsNum` | 全剧总点赞数 | /portal/1125 | "1453.9万" |
| `videoStarsNumActual` | 点赞精确值 | /portal/1125 | 14538620 |
| `bookId` | 短剧唯一 ID | 所有接口 | "41000129399" |
| `bookName` | 短剧名称 | /portal/1125, /portal/1131, /portal/1139 | "遇遇跑路" |
| `chapterId` | 单集唯一 ID | /portal/1131, /portal/1139 | "608856688" |
| `chapterList` | 全部剧集列表 | /portal/1131 | 49集数组 |
| `chapterInfo` | 指定集详情（含播放地址） | /portal/1139 | 含 content.mp4Url |
| `mp4Url` | 视频播放地址 | /portal/1131, /portal/1139 | "https://mfvideo.cbread.cn/..." |
| `likesNum` | 单集点赞数 | /portal/1131 | "271" |
| `isCharge` | 是否付费集 | /portal/1131, /portal/1139 | 0=免费, 1=付费 |
| `coverWap` | 封面图 URL | /portal/1125, /portal/1131 | "https://kyyresali.kkyd.cn/..." |
| `introduction` | 短剧简介 | /portal/1131 | "我是勇毅侯府养着的通房丫鬟..." |
| `bookTags` | 标签列表 | /portal/1125, /portal/1131 | ["女性成长", "漫剧", "古代言情"] |
| `finishStatusCn` | 完结状态 | /portal/1125, /portal/1131 | "已完结" |
| `updateNum` | 总集数 | /portal/1125, /portal/1131 | 49 |

## 接口概览

| # | 接口 | 用途 | 角色 | 请求次数 |
|---|------|------|------|----------|
| 1 | `/free-video-portal/portal/1125` | 剧场分类列表（⭐含播放量+漫剧列表） | LIST | 4 |
| 2 | `/free-video-portal/portal/1131` | 短剧详情（含剧集列表+当前集播放地址） | DETAIL | 1 |
| 3 | `/free-video-portal/portal/1139` | 切集播放信息（批量获取指定集播放地址） | EPISODE | 2 |

> **签名机制**: 所有接口通过 `sign` header 签名 + `datas` header 传递设备/用户信息（含 nonce + timestamp 防重放）。
> **采集策略**: 无法脱离 App 独立调用，需通过代理拦截方式采集。

---

## 1. `/free-video-portal/portal/1125` — 剧场分类列表（含播放量）

> 剧场页面的核心接口，返回频道分组（推荐/穿越/重生/古装/漫剧等）和频道下的短剧列表。
> **⭐ 重要：此接口返回播放量（`coverBottomTips`）和完整的漫剧列表数据。**

**方法**: `POST`
**域名**: `freevideo.zqqds.cn`
**调用次数**: 4（首次加载 + 3次分页）

### 请求参数

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `pageFlag` | `""` / `"1"` | 分页标识，空字符串=首页，数字=翻页 |
| `recSwitch` | `false` | 推荐开关 |
| `kingKongSwitch` | `false` | 金刚位开关 |
| `audioBook` | `1` | 是否包含有声书 |
| `theaterSubscriptSwitch` | `false` | 剧场订阅开关 |
| `needPlayLink` | `0` | 是否需要播放链接 |
| `isOldAgeMode` | `false` | 适老模式 |
| `resolutionRate` | `"720P"` | 分辨率 |
| `preview` | `1` | 预览模式 |

### 响应结构

📁 完整响应: [`portal_1125_response.json`](samples/portal_1125_response.json)

**data 字段结构**:

```
data:
  storePageId: 10002
  channelGroupData: [8 items]     ← 频道分组（推荐/新剧/漫剧/排行榜/听书/小说/经典好剧/北京大视听）
  columnData: [N items]           ← 当前频道的栏目数据
  hasMore: true                   ← ⭐ 分页标识：是否有更多
  pageFlag: "1"                   ← ⭐ 分页标识：下一页标记
  needConcat: false
  fromColumnId: 1
  theaterSubscriptSwitch: true
```

**channelGroupData[0] 字段**（频道分组）:

```
  channelGroupId: 65
  channelGroupName: "推荐"
  channelGroupType: "1"
  channelType: 1
  checkedFlag: true               ← 当前选中的频道
  autoRefreshTime: 30
  channelData: [{channelId, channelName, tagIds, jumpType, checkedFlag}, ...]
```

**columnData[0].videoData[0] 字段**（⭐ 漫剧列表数据）:

```
  bookName: "大夏傻神之逆袭"
  bookId: 41000108769
  coverWap: "https://kyyresali.kkyd.cn/cppartner/..."    ← 封面图
  bookTags: ["女帝", "古装", "权谋", "喜剧", "穿越"]
  finishStatusCn: "已完结"
  finishStatus: 1
  updateNum: 65                                          ← 总集数
  videoStarsNum: "1453.9万"                              ← 全剧总点赞
  videoStarsNumActual: 14538620                          ← 点赞精确值
  coverBottomTips: "7.5亿播放"                           ← ⭐ 播放量
  coverBottomType: 1
  iconType: 3
  iconName: "爆剧"
  rankActionTips: "热播榜TOP3"                           ← 排行榜标识
  rankSrc: "热度值388.8万"
  showTag: "喜剧"                                        ← 展示标签
  utime: "2026-02-04 20:02:40"                           ← 更新时间
  aiDramaMark: "漫剧"                                    ← AI漫剧标识
  aiDramaPrompt: "作者声明：内容由AI生成"
```

**播放量数据示例**（来自本次抓取）:

| 短剧名 | coverBottomTips | videoStarsNum（点赞） |
|--------|----------------|---------------------|
| 大夏傻神之逆袭 | **7.5亿播放** | 1453.9万 |
| 女凭母贵 | **3.4亿播放** | 604.5万 |
| 情感试炼 | **3.9亿播放** | 775.5万 |
| 无上贵婿 | 142.7万播放 | 6.3万 |
| 孤影绽放，宠冠加冕 | **1.7亿播放** | 409.8万 |
| 渺渺兮予怀 | **4.5亿播放** | 797.0万 |
| 男人五十 | **10.2亿播放** | 2030.9万 |
| 乡下老妈绝代风华 | 9161.7万播放 | 198.5万 |
| 嫁去农村，成为头号当家主母 | 8665.5万播放 | 210.1万 |

### cURL

📁 完整请求: [`portal_1125_request.json`](samples/portal_1125_request.json)

```bash
curl -X POST \
  'http://freevideo.zqqds.cn/free-video-portal/portal/1125' \
  -H 'alg: HG45LKBS' \
  -H 'sign: +YjZj1tpZW46vso9cwFamWo69dAgaknX1+dzpXgBDAw=' \
  -H 'datas: {"freeflow":0,"version":"3.2.2","pname":"com.dz.hmjc","channelCode":"HMJC1000004","utdidTmp":"A20260507174656796JidVoe","token":"","utdid":"27f1421956093092d73e75dafd06ed82","os":"android","osv":32,"brand":"vivo","model":"V2362A","manu":"vivo","userId":"2814651518","launch":"shortcut","mchid":"HMJC1000004","nchid":"HMJC1000004","session1":"ed7974df-37a2-4eb0-a697-e2fb968ac064","session2":"ed7974df-37a2-4eb0-a697-e2fb968ac064","startScene":"shortcut","recSwitch":false,"installTime":1778036642735,"p":53,"nonce":"01ae81fca935422498004b509ee9560c","timeZone":"Asia/Shanghai","timestamp":"1778462276038","boxId":"B3Vrc7/KgNdUTu8yK0vuT6vXHIBZsebZfg0qEVdhAxupq7w8jKi5FRx0E3mkYrKley47+pOZWQOmdlbfhDGIXRA=="}' \
  -H 'wetruwtty: mhdfiheowjfcslkjfwojo636' \
  -H 'X-Request-ID: 9346b6a2-e8e4-40dd-9c93-5a8f89e97b72' \
  -H 'Content-Type: application/json; charset=utf-8' \
  -H 'User-Agent: okhttp/4.10.0' \
  -d '{"recSwitch":false,"kingKongSwitch":false,"audioBook":1,"pageFlag":"","theaterSubscriptSwitch":false,"needPlayLink":0,"isOldAgeMode":false,"resolutionRate":"720P","preview":1}'
```

---

## 2. `/free-video-portal/portal/1131` — 短剧详情（含剧集列表+播放地址）

> 传入 bookId，返回短剧完整信息（videoInfo）、全部剧集列表（chapterList）和当前集的播放地址（mp4Url）。
> 这是进入详情页时调用的核心接口。

**方法**: `POST`
**域名**: `freevideo.zqqds.cn`
**调用次数**: 1

### 请求参数

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `bookId` | `"41000129399"` | 短剧 ID（从列表接口获取） |
| `needNextChapter` | `0` | 是否需要下一集信息 |
| `playSourceL1` | `"剧场"` | 播放来源一级 |
| `playSourceL2` | `"剧场-漫剧"` | 播放来源二级 |
| `playSourceL3` | `"剧场-漫剧"` | 播放来源三级 |
| `resolutionRate` | `"720P"` | 分辨率 |
| `preview` | `1` | 预览模式 |
| `commentType` | `2` | 评论类型 |
| `excludeInfo` | `0` | 排除信息 |
| `screenClearType` | `3` | 清屏类型 |
| `bottomStyle` | `2` | 底部样式 |

### 响应结构

📁 完整响应: [`portal_1131_response.json`](samples/portal_1131_response.json)

**data 字段结构**:

```
data:
  status: 1
  inBookShelf: false
  videoInfo: {...}                 ← 短剧完整信息
  chapterList: [49 items]         ← ⭐ 全部剧集列表
  isVip: false
  freeNotificationSwitch: 0
```

**videoInfo 字段**（短剧详情）:

```
  bookId: "41000129399"
  bookName: "遇遇跑路"
  author: ""
  coverWap: "https://kyyresali.kkyd.cn/cppartner/..."
  introduction: "我是勇毅侯府养着的通房丫鬟..."      ← 短剧简介
  protagonist: ["夜瑾辰", "玉瑾"]                    ← 主角
  updateNum: 49                                      ← 总集数
  finishStatusCn: "已完结"
  bookTags: ["女性成长", "漫剧", "古代言情", "虐恋", "仿真人动态漫", "逆袭"]
  videoStarsNum: "6401"                              ← 总点赞
  chapterIndex: 1                                    ← 当前集
  chapterId: "608856688"
  maxChapterId: "608856736"
  maxChapterName: "第四十九集"
  content:
    mp4Url: "https://mfvideo.cbread.cn/..."          ← ⭐ 当前集播放地址
    mp4SwitchUrl: [3个备用地址]
    mp4UrlRate: "720P"
    resolutionRates: [{rate, needVip, describe}, ...]
    commentNum: 16
```

**chapterList[0] 字段**（剧集列表项）:

```
  chapterIndex: 1
  chapterId: "608856688"
  chapterName: "第一集"
  isCharge: 0                     ← 0=免费, 1=付费
  price: 0
  likesNum: "271"
  likesNumActual: 271
  likesChecked: false
```

### cURL

📁 完整请求: [`portal_1131_request.json`](samples/portal_1131_request.json)

```bash
curl -X POST \
  'http://freevideo.zqqds.cn/free-video-portal/portal/1131' \
  -H 'alg: HG45LKBS' \
  -H 'sign: oI2wm1dmcKQ5eyuCRIWfMq4bTA6kSyAeT9iebk5alcc=' \
  -H 'datas: {"freeflow":0,"version":"3.2.2","pname":"com.dz.hmjc",...}' \
  -H 'wetruwtty: mhdfiheowjfcslkjfwojo636' \
  -H 'Content-Type: application/json; charset=utf-8' \
  -H 'User-Agent: okhttp/4.10.0' \
  -d '{"bookId":"41000129399","needNextChapter":0,"isNeedAlias":"","bookAlias":"","playSourceL1":"剧场","playSourceL2":"剧场-漫剧","playSourceL3":"剧场-漫剧","resolutionRate":"720P","preview":1,"commentType":2,"excludeInfo":0,"screenClearType":3,"bottomStyle":2,"showOriginNovel":0}'
```

---

## 3. `/free-video-portal/portal/1139` — 切集播放信息

> 切换剧集时调用，传入 bookId + chapterIds（批量），返回指定集的播放地址和评论数。
> 每次预加载 4 集的播放信息。

**方法**: `POST`
**域名**: `freevideo.zqqds.cn`
**调用次数**: 2

### 请求参数

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `bookId` | `"41000129399"` | 短剧 ID |
| `chapterId` | `"608856688"` | 当前播放的集 ID |
| `chapterIds` | `["608856689","608856690","608856691","608856692"]` | ⭐ 批量预加载的集 ID 列表 |
| `unClockType` | `"load"` | 解锁类型 |
| `tierPlaySource` | `{"firstTierPlaySource":"剧场",...}` | 播放来源 |
| `resolutionRate` | `"720P"` | 分辨率 |
| `preview` | `1` | 预览模式 |
| `playPercentage` | `0.0` | 播放进度 |
| `continuousAd` | `0` | 连续广告 |
| `commentType` | `2` | 评论类型 |

### 响应结构

📁 完整响应: [`portal_1139_response.json`](samples/portal_1139_response.json)

**data 字段结构**:

```
data:
  bookStatus: "上架"
  bookFinishStatus: 1
  maxChapter: 49
  bookName: "遇遇跑路"
  bookId: "41000129399"
  isVip: false
  payType: "预加载"
  chapterInfo: [4 items]          ← ⭐ 批量返回的集播放信息
  isInBookShelf: false
  sysTime: 1778462297861
  status: 1
```

**chapterInfo[0] 字段**（单集播放详情）:

```
  chapterId: "608856689"
  chapterName: "第二集"
  chapterIndex: 2
  chapterImg: "https://dzzt-video.cbread.cn/..."     ← 集封面图
  commentNum: 13                                      ← 评论数
  isCharge: 0                                         ← 0=免费
  chapterStatus: 1
  content:
    mp4Url: "https://mfvideo.cbread.cn/..."           ← ⭐ 播放地址
    mp4SwitchUrl: [3个备用地址]
    mp4UrlRate: "720P"
    resolutionRates: [{rate:"1080P",needVip:1}, {rate:"720P",needVip:0}, {rate:"540P",needVip:0}]
    spriteImg: "https://dzzt-video.cbread.cn/...vtt"  ← 雪碧图（进度条预览）
```

### cURL

📁 完整请求: [`portal_1139_request.json`](samples/portal_1139_request.json)

```bash
curl -X POST \
  'http://freevideo.zqqds.cn/free-video-portal/portal/1139' \
  -H 'alg: HG45LKBS' \
  -H 'sign: TnVIs1MGudaJdRTQdF0mOa8jQlQqgYhAf4SUtCkjbLQ=' \
  -H 'datas: {"freeflow":0,"version":"3.2.2","pname":"com.dz.hmjc",...}' \
  -H 'wetruwtty: mhdfiheowjfcslkjfwojo636' \
  -H 'Content-Type: application/json; charset=utf-8' \
  -H 'User-Agent: okhttp/4.10.0' \
  -d '{"bookId":"41000129399","chapterIds":["608856689","608856690","608856691","608856692"],"unClockType":"load","chapterId":"608856688","tierPlaySource":{"firstTierPlaySource":"剧场","secondTierPlaySource":"剧场-漫剧","thirdTierPlaySource":"剧场-漫剧"},"resolutionRate":"720P","preview":1,"playPercentage":0.0,"continuousAd":0,"commentType":2}'
```

---

## 签名机制说明

所有接口使用相同的签名机制：

| Header | 说明 |
|--------|------|
| `alg` | 签名算法标识，固定值 `HG45LKBS` |
| `sign` | 动态签名值（Base64 编码），每次请求不同 |
| `datas` | JSON 字符串，包含设备信息 + 用户信息 + 防重放参数 |
| `wetruwtty` | 固定值 `mhdfiheowjfcslkjfwojo636` |

**datas 中的关键字段**：
- `nonce`: 随机字符串（防重放）
- `timestamp`: 时间戳（防重放）
- `boxId`: 加密的设备标识
- `userId`: 用户 ID
- `token`: 登录 Token（未登录为空）
- `version`: App 版本 "3.2.2"
- `pname`: 包名 "com.dz.hmjc"

**结论**：所有接口包含动态签名，无法脱离 App 独立调用。采集需通过代理拦截方式。

## 采集策略建议

1. **列表数据采集**：通过 `/portal/1125` 接口翻页（修改 pageFlag），可获取全部漫剧列表含播放量
2. **详情数据采集**：从列表中提取 bookId，调用 `/portal/1131` 获取剧集列表
3. **播放地址采集**：从剧集列表中提取 chapterId，调用 `/portal/1139` 批量获取播放地址
4. **签名限制**：所有接口有 sign 签名，需要通过代理拦截方式采集，无法直接用 requests 调用
5. **分页策略**：`/portal/1125` 支持 pageFlag 分页，hasMore=true 时继续翻页
