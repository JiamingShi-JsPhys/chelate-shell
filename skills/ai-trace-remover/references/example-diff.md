# 改写前后对照（4 个真实场景）

> 每个场景给三段：**Before（AI 体）→ After（人话）→ 改了什么**。用于校准手感，不是模板。
> 跨语言：中文场景对照 `ai-patterns-zh.md`，英文场景对照 `ai-patterns-en.md`。

---

## 场景 1 · 技术博客（中文，去 AI 味）

**Before：**
> 在当今数字化浪潮下，AI 技术的重要性日益凸显。随着大模型的发展，赋能各行业已成为共识。
> 我们认为，深耕底层逻辑、构建全链路闭环，是每一位从业者亟需掌握的核心能力。
> 让我们一起在智能化的道路上砥砺前行，共同谱写新篇章！

**After：**
> 去年我们给客服系统接了个大模型，第一周误判率高得离谱，客服要手动纠正一半的回复。
> 问题出在 prompt 里没给例子——模型靠猜。补上 20 条真实对话样本后，误判率从 40% 降到 9%。
> 下个季度打算把纠错数据回灌进微调，目标是 5%。

**改了什么：**
- 砍掉"在当今数字化浪潮下""日益凸显"（A1 开头套话）
- "赋能""深耕底层逻辑""全链路闭环"→ 换成具体动作 + 数字（A6 黑话 + A5 排比）
- "让我们一起……砥砺前行，共同谱写新篇章"→ 具体计划（A4 结尾升华，硬禁令）
- 补 3 个具体数字（40%、9%、5%）和 1 个来路（去年、第一周），过声音五条第 1、2、5 条

---

## 场景 2 · 新闻/行业解读（中文，模糊归因 → 具体出处）

**Before：**
> 业内人士普遍认为，新能源行业正迎来爆发式增长。据相关数据显示，市场规模将持续扩大。
> 这一趋势是产业升级的体现，彰显了行业创新的活力。

**After：**
> 2024 年中国新能源汽车销量 1,200 万辆，比 2023 年翻了近一倍（中汽协口径）。
> 增速放缓的主因是渗透率过了 30%——基数大了，环比当然没 2023 年猛。

**改了什么：**
- "业内人士普遍认为""据相关数据显示"→ 具体机构 + 具体数字（A7 模糊归因）
- "爆发式增长""持续扩大"→ 真实数字（A3 官腔 + A9 假大空）
- "是产业升级的体现，彰显了……活力"→ 删（A8 伪深度，硬禁令）

---

## 场景 3 · 产品文案（英文，promotion → fact）

**Before:**
> Seamlessly crafted and designed for everyday life, our flagship device stands as a vibrant
> testament to the industry's enduring commitment to innovation. It boasts a rich display and
> showcases how technology can truly transform the way we live, marking a key turning point in
> the evolving landscape of personal computing.

**After:**
> The 40-hour battery was the spec we pushed hardest on. After the first prototype drained in
> six hours, the firmware team rewrote the power model and got it to a full workday, which we
> verified with a week of logged usage before shipping.

**改了什么:**
- "stands as a vibrant testament to ... commitment to innovation"（E1 膨胀）、"a key turning
  point in the evolving landscape"（E1）→ 删膨胀句式
- "boasts a rich display"（E4 营销体）、"showcases how technology can truly transform"
  （E3 伪深度 -ing）→ 换真实工程数字（40 小时、6 小时、一周日志）

---

## 场景 4 · 人物故事（中文，补声音、不过度抒情）

**Before：**
> 张师傅的故事，是无数基层劳动者坚韧不拔精神的缩影。他用三十年的坚守，诠释了什么是真正的工匠精神。
> 在他的身上，我们看到了普通人的伟大，也看到了时代前行的力量。

**After：**
> 张师傅修了三十年锅炉，手上烫疤叠了七层。去年厂里想淘汰他那个 1998 年的老型号，他不同意，
> 说那台机器的异响"听着就知道哪儿漏气"。最后厂里留了那台，也留了他——他 61 了，还在班。

**改了什么:**
- "是……精神的缩影""诠释了什么是真正的工匠精神"（A8 伪深度）→ 删
- "我们看到了普通人的伟大，也看到了时代前行的力量"（A4 结尾升华 + 表演性抒情）→ 删
- 补 3 个具体细节（烫疤七层、1998 年型号、61 岁），保留 1 处不确定感（"说不准"可再加），过声音五条

---

## 蒸馏版（可直接粘进任意聊天窗口）

> 改的时候只做四件事：删开头套话、删结尾升华、删模糊归因和伪深度句；补具体数字、补具体
> 名词、补说话人身份、补一处不确定性。改完朗读一遍，卡壳就拆短句。不要为了"像人"硬加
> "我觉得""说真的"，声音来自取舍，不来自代词。
