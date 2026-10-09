# 公共机器人维护分支

分支：`codex/public-bot-server`

上游基准：`87c06f11ae10c12b3bb8e76b3c6f420c831282a8`

保留公共群扫码登录的游戏 UID 归属验证与口令前缀，以及查询错误不缓存的修复。QQ 官方接入端、请求者身份转换与排队业务仍由 zzz-queue-obs 项目负责。

主项目：[zzz-queue-obs](https://github.com/Karl-Cao/zzz-queue-obs)。配置、用户数据库、Cookie、Stoken、机器人密钥、日志和下载的资源目录未作为本次修改提交。此分支归档已部署补丁；fork 本身不会自动切换线上服务，上游默认分支保留供同步。
