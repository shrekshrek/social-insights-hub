"""行业研究 Profile — Planner 节点上下文"""

PLANNER_CONTEXT = """⚠️ 重要：本次搜索的目标是找到可下载的专业研究报告（PDF/白皮书），而非普通网页文章。

关键词生成规则：
- 每个关键词必须包含"报告""白皮书""研究报告""PDF"等报告类修饰词
- 示例："2024新能源汽车行业报告 PDF"、"中国消费市场白皮书"、"XX行业研究报告"
- 同时生成中英文关键词：如 "China EV market report 2024"

可选的目标域名参考（不限于此，请根据主题补充更多）：

综合咨询/四大（⚠️ 注意子域名：PDF 报告通常托管在子域名，需两个一起推荐才能被搜索到）：
- mckinsey.com.cn + mckinsey.com（麦肯锡，前者中文本土化报告，后者英文全球报告）
- deloitte.com（德勤）
- pwccn.com（普华永道中国）
- ey.com（安永）
- kpmg.com + assets.kpmg.com（毕马威，assets 子域托管 PDF 报告）
- bcg.com + media-publications.bcg.com（波士顿咨询，media-publications 子域托管出版物）
- bain.com + media.bain.com（贝恩，media 子域托管报告）
- rolandberger.com（罗兰贝格）
- accenture.com（埃森哲）
- oliverwyman.com（奥纬咨询）
- kearney.com（科尔尼）

政府/智库：
- cssn.cn（社科院）
- drc.gov.cn（国研中心）
- stats.gov.cn（国家统计局）
- cnnic.net.cn（中国互联网络信息中心，互联网行业权威半年报，PDF 直接下载）
- miit.gov.cn（工业和信息化部，工业/互联网/通信行业月度运行数据）
- pbc.gov.cn（中国人民银行，货币政策/金融/支付行业数据）
- ndrc.gov.cn（国家发展改革委，产业政策/五年规划/行业分析）
- mofcom.gov.cn（商务部，对外贸易/外资/消费数据）
- csrc.gov.cn（证监会，资本市场/上市公司监管数据）

上市公司披露（⭐ 适用于"某行业市场规模/竞争格局"类问题，不适合买方行为/决策流程类问题）：
- cninfo.com.cn（巨潮资讯，A股年报/招股书全库；招股书"行业概况"章节含 Frost & Sullivan、灼识等机构的付费数据，完全免费）
- hkexnews.hk（港交所披露易，港股公司年报及招股书；⚠️ 仅在研究行业市场数据时推荐，搜索结果以公告新闻为主）
- sse.com.cn（上交所公告及行业信息披露；同上，仅限行业数据类问题）

行业研究（完全免费或有完整免费报告）：
- iresearch.cn + report.iresearch.cn（艾瑞咨询，report 子域托管 PDF 报告下载，需两个一起推荐）
- questmobile.com.cn（QuestMobile，有完整免费季度报告，App/移动互联网数据）
- aliresearch.com（阿里研究院，数字经济/电商行业报告，完全免费）
- mob.com（Mob研究院，消费者行为/App行业免费报告）
- research.hktdc.com（香港贸易发展局，中国各省市场+跨境贸易报告，完全免费）
- caict.ac.cn（信通院，ICT 白皮书/行业报告，完全免费）
- cesi.cn（中国电子标准化研究院，数字化/信息化标准与报告）

注意：euromonitor、frost、grandviewresearch、mordorintelligence、analysys、askci、cbndata、qianzhan 等为高价订阅制，报告正文无法获取，请勿推荐。

垂直媒体/深度报道（完全免费）：
- 36kr.com（36氪研究院，科技/创投领域研究报告）
- latepost.com（晚点LatePost，深度商业调查报道）
- caam.org.cn（中国汽车工业协会，月度产销数据摘要，仅汽车行业）
- ccfa.org.cn（中国连锁经营协会，零售行业报告，仅零售行业）

国际数据/消费者研究（完全免费）：
- oecd.org（OECD，2024年起全面免费开放，跨国行业对标与政策比较）
- unctad.org（联合国贸发会，全球贸易/FDI/新兴市场数据）
- documents.worldbank.org + openknowledge.worldbank.org（世界银行，两个文档库内容不同，均可推荐）
- imf.org（IMF，全球宏观经济/金融稳定报告）
- wto.org（WTO，全球贸易统计与政策报告）
- adb.org（亚开行，亚太地区发展报告）
- datareportal.com（每年发布全球数字消费者报告，640页完全免费）
- pewresearch.org（皮尤研究中心，全球消费者/技术态度调查，完全免费）
- ourworldindata.org（牛津全球数据，CC-BY开放，13000+图表及原始数据）

买方行为/独立研究机构（适用于"企业如何选择服务商"类研究）：
- edelman.com（爱德曼信任晴雨表，研究B2B信息渠道与决策信任，完全免费）
- gartner.com（企业服务采购与供应商评估研究，摘要页可抓取）
- forrester.com（B2B 买方旅程与决策行为研究，摘要页可抓取）
- business.linkedin.com（LinkedIn B2B 决策者行为洞察报告）

⚠️ 通用原则：来源视角应与研究视角匹配。
- 研究"行业现状/市场规模/竞争格局"→优先第三方数据机构、政府统计、上市公司招股书
- 研究"用户/买方行为/决策流程"→优先独立调研机构（Edelman、Gartner、LinkedIn 等），行业参与者自身发布的内容（卖方视角）无法回答买方问题
- 研究"技术/产品/政策"→参与者自身发布的年报、白皮书具有一手价值
请根据具体研究问题判断哪类来源最能回答该问题，不要默认权威机构的内容就是最相关的。

请根据具体研究主题，补充该领域特有的权威机构域名。"""
