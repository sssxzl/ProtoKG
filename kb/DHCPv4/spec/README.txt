DHCPv4 协议规范 RFC 清单与内容说明
==================================================
来源: https://www.rfc-editor.org/rfc/rfcNNNN.txt  (RFC Editor 官方纯文本版)
格式: 纯文本 .txt, 命名 rfcNNNN.txt (与 kb/rtsp、kb/sip、kb/smtp 规范目录保持一致)
编码: ASCII / UTF-8 无 BOM, CRLF 行尾
共计: 36 个文件, 约 1.1 MB

【收录原则】
只收录官方索引中状态为现行有效 (DRAFT STANDARD / PROPOSED STANDARD /
INFORMATIONAL / BEST CURRENT PRACTICE) 的文档。已被 Obsoleted 的历史版本
移至上级目录 _obsolete_backup/。
注意: rfc951 / rfc1534 / rfc1542 发布年代久远, 但状态仍是现行 DRAFT STANDARD,
未被任何 RFC 取代, 故予以保留。

【阅读路径建议】
想了解协议全貌, 建议依次读:
  rfc951 (BOOTP 报文格式源头) -> rfc1542 (BOOTP 澄清) -> rfc2131 (DHCP 主体)
  -> rfc2132 (选项定义) -> rfc3396 (长选项编码规则)
其余为针对特定场景的扩展, 按需查阅。


==================================================
一、核心协议规范
==================================================

rfc951.txt  Bootstrap Protocol (BOOTP)                          1985-09
   DHCP 的前身协议, 定义了 BOOTP 报文格式与引导流程。核心内容包括:
   两阶段引导模型(第一阶段地址确定与引导文件选择, 第二阶段经 TFTP 传输文件)、
   固定长度 300 字节的报文结构(op/vendor/bootp fields)、magic cookie
   0x63825363 的引入、客户端用 ARP 做地址冲突检测("Chicken/Egg" 问题)、
   与 RARP 的对比, 以及经网关引导(第 8 节)。DHCP 的报文头、vendor 字段
   封装与中继机制均可追溯至此。

rfc1534.txt Interoperation Between DHCP and BOOTP                1993-10
   说明 DHCP 与 BOOTP 参与者之间的互操作行为。DHCP 是 BOOTP 功能的超集,
   两者可共存于同一网络。本文界定 BOOTP 客户端与 DHCP 服务器、DHCP 客户端
   与 BOOTP 服务器之间交互时的报文格式兼容规则与回退行为, 现行有效。

rfc1542.txt Clarifications and Extensions for the Bootstrap Protocol  1993-10
   澄清并强化 BOOTP 原始规范中定义过于松散的部分, 重点是 BOOTP 中继代理
   (原称 forwarding agent)的行为规范与客户端行为描述。因 RFC 1532 在编辑
   过程中引入错误, 本文作为其重发版本。BOOTP 领域的现行有效文档。

rfc2131.txt Dynamic Host Configuration Protocol                  1997-03
   DHCP 主规范, 整个协议体系的核心。规定 DHCP 的四步交互流程
   (DISCOVER / OFFER / REQUEST / ACK)、租期管理与状态机
   (INIT / SELECT / REQUEST / BOUND / RENEW / REBIND)、续租与重绑定时序、
   BOOTP 中继代理行为、客户端标识与报文校验和(checksum)计算规则,
   以及 INFORM 消息(仅获取配置、不申请地址)的使用场景。
   本文取代 RFC 1541, 并被 rfc3396、rfc4361、rfc6842 等更新修订。

rfc2132.txt DHCP Options and BOOTP Vendor Extensions             1997-03
   DHCP 选项定义规范。规定选项的 TLV 格式(Code / Len / Data)、选项重载
   (option overloading)与 padding/end 选项(255)、options 字段在报文中的
   承载方式, 并逐个定义当时的全部标准选项, 例如:
     code 1   Subnet Mask            子网掩码(长度 4)
     code 3   Router                 路由器地址列表(长度须为 4 的倍数)
     code 12  Host Name              主机名
     code 15  Domain Name            域名
     code 50  Requested IP Address   客户端请求的 IP 地址
     code 51  IP Address Lease Time  租期(长度 4)
     code 53  Message Type           报文类型(长度 1, 取值 1-9:
               DISCOVER/OFFER/REQUEST/DECLINE/ACK/NAK/RELEASE/INFORM)
     code 54  Server Identifier       服务器标识(长度 4)
     code 55  Parameter Request List  参数请求列表
     code 61  Client Identifier       客户端标识(长度 2, 即硬件类型)
   本文取代 RFC 1533, 并被 rfc3442、rfc4361、rfc4833 等更新修订。


==================================================
二、核心规范的修订与登记
==================================================

rfc3396.txt Encoding Long Options in DHCPv4                        2002-11
   规定 DHCPv4 中同一选项多次出现时的拼接处理规则。当选项超过 255 字节
   (单个选项长度上限), 或需要借助选项重载机制拆分时, 会产生多个同码实例;
   本规范规定这些实例的内容须按顺序拼接还原为单一逻辑值。更新 RFC 2131,
   是正确解析超长选项的必要依据。

rfc3442.txt The Classless Static Route Option for DHCPv4          2002-12
   定义 code 121 Classless Static Route 选项, 用于下发无类别静态路由表。
   路由表项不含掩码字段, 而是由 "目的前缀/子网掩码长度" 形式表达, 长度
   须为 12 的倍数。更新 RFC 2132。

rfc4361.txt Node-specific Client Identifiers for DHCPv4           2006-02
   规范 DHCPv4 客户端标识的编码格式, 使其与 DHCPv6 的客户端标识可互换。
   同时修正 RFC 2131 与 RFC 2132 中关于客户端标识处理的若干问题。
   更新 RFC 2131、2132、3315。

rfc6842.txt Client Identifier Option in DHCP Server Replies        2013-01
   修正 RFC 2131 中"服务器 MUST NOT 在应答中返回 client identifier 选项"
   这一规定所引发的问题。更新 RFC 2131。

rfc3679.txt Unused DHCP Option Codes                             2004-01
   列出 RFC 2489 时期曾分配但从未实际使用的 DHCP 选项码, 并请 IANA 释放
   这些码位以供未来重新分配。属信息类文档, 是判断"某选项码为何空缺"的
   直接依据。后被 rfc8910 更新。

rfc8910.txt Captive-Portal Identification in DHCP and RAs          2020-09
   定义用于标识 Captive-Portal(强制门户)环境的 DHCP 选项(及配套的 IPv6
   RA 选项), 供客户端判断自身是否处于强制门户认证状态, 从而抑制在认证
   完成前访问外网。取代 RFC 7710, 更新 RFC 3679。

rfc2939.txt Procedures and IANA Guidelines for Definition of New
          DHCP Options and Message Types                            2000-09
   新 DHCP 选项与消息类型的定义流程与 IANA 分配指南, 属 BCP 43。
   规定选项码的申请、分配与登记规则, 是扩展选项时必须遵循的流程。
   取代 RFC 2489。


==================================================
三、消息与选项扩展
==================================================

rfc2563.txt DHCP Option to Disable Stateless Auto-Configuration in
          IPv4 Clients                                                 1999-05
   定义 code 116 选项, 供客户端声明自己不使用 IPv4 链路本地地址自动配置。
   适用于无中心配置(ad-hoc)网络场景, 且修正了"主机无 DHCP 应答即无 IP"
   这一传统假设。后被 rfc8925 更新。

rfc2937.txt The Name Service Search Option for DHCP               2000-09
   定义 code 117 Domain Search 选项, 由服务器下发, 规定客户端解析主机名时
   应依次咨询的名称服务器顺序列表。文中同时给出各名称服务的既有选项码对照
   (Domain Name Server 6、NIS 41、NetBIOS 44、NIS+ 65), 并约定选项码 0 表示
   客户端应参考本地命名信息(如 /etc/hosts)。

rfc3004.txt The User Class Option for DHCP                         2000-11
   定义 code 77 User Class 选项。客户端借此声明自身所属的用户或应用类别,
   服务器据此选择相应的地址池与配置参数下发。该选项应可由用户配置。

rfc3011.txt The IPv4 Subnet Selection Option for DHCP              2000-11
   定义 code 118 Subnet Selection 选项, 允许客户端显式指定希望分配地址的
   子网, 覆盖服务器原有的子网选择逻辑。

rfc3361.txt DHCP-for-IPv4 Option for SIP Servers                   2002-08
   定义 code 120 选项, 内容为域名或 IPv4 地址列表, 用于映射到一个或多个
   SIP 出站代理服务器, 是 SIP 客户端获知本地 SIP 服务器地址的途径之一。

rfc3442.txt (见上, 二、核心规范的修订与登记)                       2002-12
   classless 静态路由选项 code 121。

rfc3456.txt DHCPv4 Configuration of IPsec Tunnel Mode              2003-01
   探讨 IPsec 隧道模式下的主机配置需求, 并说明如何借助 DHCPv4 完成配置。
   典型场景是远程接入主机从企业网获得"虚拟"地址, 再由 ISP 分配地址经
   IPsec 隧道回传至企业安全网关。

rfc3495.txt DHCP Option for CableLabs DHCPv4                       2003-04
   定义用于配置 CableLabs 架构设备的 DHCP 选项, 首期覆盖 PacketCable
   Media Terminal Adapter (MTA) 这一类客户端, 后续客户端类型在此基础上扩展。

rfc4702.txt The DHCP Client FQDN Option                            2006-10
   定义 code 81 选项, 用于交换 DHCPv4 客户端的完全限定域名, 以及由谁负责
   更新客户端地址对应的 DNS 记录。是 FQDN 与地址分配绑定的关键选项。

rfc4776.txt DHCP Option for Civic Addresses                       2007-11
   定义包含客户端或服务器"公民地址"的位置配置信息(LCI)的选项, 涵盖国家、
   省州与城市等行政区划、街道地址、邮政社区名及建筑物信息, 并支持同一
   地址以不同文字与语言的多重呈现形式。

rfc4833.txt Timezone Options for DHCP                              2007-04
   定义两类时区选项, 分别承载 POSIX 1003.1 时区字符串与时区数据库名称;
   同时弃用原有的 DHCPv4 time offset 选项。更新 RFC 2132。

rfc3925.txt Vendor-Identifying Vendor Options for DHCPv4          2004-10
   定义两个新选项, 参照 IPv6 的厂商类与厂商特定信息选项, 通过携带
   Enterprise Number 消除"一个客户端代表多个厂商"时原有 Vendor Class 与
   Vendor-Specific Information 选项的歧义。

rfc8925.txt IPv6-Only Preferred Option for DHCPv4                 2020-10
   定义 code 108 IPv6-Only Preferred 选项, 表明主机支持 IPv6-only 模式, 愿意
   在网络提供 IPv6 连通性时放弃获取 IPv4 地址。选项长度固定为 4 字节, 值为
   32 位无符号整数, 表示客户端应禁用 DHCPv4 的秒数(V6ONLY_WAIT 配置变量);
   客户端须将该 Code 列入 DHCPDISCOVER 与 DHCPREQUEST 的 Parameter Request
   List, 长度字段非 4 时客户端应忽略该选项。同时更新 RFC 2563, 规定服务器在
   收到不含 Auto-Configure 选项但含该新选项的 DHCPDISCOVER 时的行为。


==================================================
四、认证 / 中继 / 重配置
==================================================

rfc3118.txt Authentication for DHCP Messages                      2001-06
   定义 DHCP 认证机制, 通过新增选项承载授权票据(authorization ticket),
   使仅授权主机可从认证过的 DHCP 服务器自动获取配置, 并支持对报文来源的
   认证。属现行的 DHCP 认证方案规范。

rfc3046.txt DHCP Relay Agent Information Option                   2001-01
   定义 code 82 Relay Agent Information 选项及其子选项, 用于将中继代理
   收集的信息(如链路选择、虚拟子网)传递给 DHCP 服务器, 解决公共接入场景
   下"公共 DHCP"面临的安全与扩展性问题。是中继代理信息传递的基准规范。

rfc5010.txt The DHCPv4 Relay Agent Flags Suboption               2007-09
   定义中继代理信息选项的子选项 code 10 Relay Agent Flags, 供中继代理
   标记所转发报文的属性, 其中一个标志位指示该报文最初是经单播还是广播
   收到, 供服务器据此更精细地服务客户端。

rfc6607.txt Virtual Subnet Selection Options                      2012-04
   定义 DHCPv4 虚拟子网选择(VSS)选项、DHCPv6 VSS 选项, 以及承载于 DHCPv4
   中继代理信息选项中的 VSS 与 VSS-Control 子选项, 用于在多归属网络中将
   虚拟子网信息传递给服务器以完成正确的地址或前缀分配。更新 RFC 3046。

rfc3203.txt DHCP reconfigure extension                           2001-12
   定义 DHCP 重配置扩展, 引入单播 FORCERENEW 报文, 由服务器触发对单个
   客户端的动态重配置(如变更 IP 地址或本地配置参数), 客户端收到后转入
   RENEW 状态。同时描述了使用 INFORM 消息获取配置的主机在该机制下的行为。
   后被 rfc6704 更新。

rfc6704.txt Forcerenew Nonce Authentication                       2012-08
   定义 Forcerenew 随机数认证机制: 服务器在初始 DHCP ACK 中下发 nonce,
   客户端后续发起 FORCERENEW 时须携带该值供服务器校验, 防止伪造的
   重配置报文。更新 RFC 3203。

rfc8357.txt Generalized UDP Source Port for DHCP Relay            2018-03
   定义 DHCP 中继代理使用任意可用源端口进行上游通信的扩展, 并引入
   OPTION_RELAY_PORT(选项码 135), 用于无状态地将响应路由回下游对应的
   源端口, 从而规避固定 67/68 端口的冲突与限制。

rfc3256.txt The DOCSIS Device Class DHCP Relay Agent Suboption    2002-04
   为中继代理信息选项定义新的子选项, 承载 DOCSIS 有线调制解调器所属的
   "设备类别"。调制解调器经 DOCSIS 信令向中继代理声明设备类别, 中继代理
   转交服务器, 服务器据此作策略决策。

rfc3074.txt DHC Load Balancing Algorithm                          2001-02
   提出一种算法化负载均衡方法, 允许多台协作服务器在初始配置之后、无需
   任何额外信息交换的前提下, 自行判定应由哪台服务器为某客户端服务。


==================================================
五、较新扩展 (2023 年以后)
==================================================

rfc9445.txt RADIUS Extensions for DHCP-Configured Services         2023-08
   定义两个新的 RADIUS 属性, 用于承载 DHCP 选项内容。规范本身是通用的,
   可适用于任何依赖 DHCP 的服务场景, 同时覆盖 DHCPv4 与 DHCPv6 配置的服务。

rfc9463.txt DHCP and Router Advertisement Options for the
          Discovery of Network-designated Resolvers (DNR)          2023-11
   定义新的 DHCP 与 IPv6 RA 选项, 用于发现加密 DNS 解析器
   (DNS over HTTPS / TLS / QUIC)。主机可借此获知认证域名(Authentication
   Domain Name)及对应的 IP 地址列表与服务参数集。

rfc9928.txt DHCPv4 over DHCPv6 with Relay Agent Support            2026-03
   描述在仅有 IPv4 的传统客户端场景下, 通过中继代理使用 DHCPv6 承载
   DHCPv4 服务的机制。RFC 7341 仅规范了客户端侧的 DHCPv4-over-DHCPv6
   封装, 本文将封装与解封装扩展到中继代理侧, 由中继代理代客户端完成
   DHCPv4 消息在 DHCPv6 消息中的封装与解封装。本目录中最新的一份文档。


==================================================
